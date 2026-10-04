<?php
declare(strict_types=1);

/** Website records only. This module never starts machines, charges cards or sends messages. */
final class BusinessPortal
{
    public const READS = ['business-orders', 'business-tickets', 'business-updates', 'business-file', 'business-dashboard', 'business-manifest'];
    public const WRITES = ['business-request', 'business-upload', 'business-proof', 'business-approve', 'business-receive', 'business-reserve', 'business-release', 'business-build', 'business-qc', 'business-fulfill', 'business-cancel', 'business-ticket', 'business-reply', 'business-task'];
    private array $moved = [];

    public function __construct(private PDO $db, private array $config, private string $storage, private array $user)
    {
        if (($config['business_enabled'] ?? false) !== true) {
            throw new PortalError('Build requests and team operations are waiting for server setup.', 503);
        }
        $db->exec(<<<'SQL'
            CREATE TABLE IF NOT EXISTS business_orders (
                id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), configuration TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'REQUESTED', revision INTEGER NOT NULL DEFAULT 1,
                quote_cents INTEGER, proof_id TEXT, approved_proof_id TEXT, production_file_id TEXT,
                finance_reference TEXT, machine TEXT, scheduled_at INTEGER, scheduled_end INTEGER,
                qc_note TEXT, carrier TEXT, tracking TEXT, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS business_orders_owner ON business_orders(user_id, created_at);
            CREATE TABLE IF NOT EXISTS business_files (
                id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES business_orders(id), uploader_id INTEGER NOT NULL REFERENCES users(id),
                purpose TEXT NOT NULL, name TEXT NOT NULL, mime TEXT NOT NULL, bytes INTEGER NOT NULL,
                sha256 TEXT NOT NULL, filename TEXT NOT NULL UNIQUE, created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS business_proofs (
                id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES business_orders(id), version INTEGER NOT NULL,
                summary TEXT NOT NULL, file_id TEXT NOT NULL REFERENCES business_files(id), quote_cents INTEGER NOT NULL,
                creator_id INTEGER NOT NULL REFERENCES users(id), created_at INTEGER NOT NULL, UNIQUE(order_id, version)
            );
            CREATE TABLE IF NOT EXISTS business_stock (
                id INTEGER PRIMARY KEY, sku TEXT NOT NULL, name TEXT NOT NULL, lot TEXT NOT NULL, location TEXT NOT NULL,
                unit TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity >= 0), threshold INTEGER NOT NULL CHECK(threshold >= 0),
                cost_cents INTEGER NOT NULL CHECK(cost_cents >= 0), quality TEXT NOT NULL, UNIQUE(sku, lot)
            );
            CREATE TABLE IF NOT EXISTS business_reservations (
                order_id TEXT NOT NULL REFERENCES business_orders(id), stock_id INTEGER NOT NULL REFERENCES business_stock(id),
                quantity INTEGER NOT NULL CHECK(quantity > 0), PRIMARY KEY(order_id, stock_id)
            );
            CREATE TABLE IF NOT EXISTS business_movements (
                id INTEGER PRIMARY KEY, stock_id INTEGER NOT NULL REFERENCES business_stock(id), order_id TEXT,
                kind TEXT NOT NULL, quantity INTEGER NOT NULL, cost_cents INTEGER NOT NULL, actor_id INTEGER NOT NULL, created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS business_events (
                id INTEGER PRIMARY KEY, order_id TEXT, actor_id INTEGER NOT NULL, kind TEXT NOT NULL,
                detail TEXT NOT NULL, customer_message TEXT, created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS business_tasks (
                id INTEGER PRIMARY KEY, reference TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'OPEN', note TEXT, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
                UNIQUE(reference, kind)
            );
            CREATE TABLE IF NOT EXISTS business_tickets (
                id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), order_id TEXT,
                kind TEXT NOT NULL, subject TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'OPEN', created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS business_messages (
                id INTEGER PRIMARY KEY, ticket_id TEXT NOT NULL REFERENCES business_tickets(id),
                actor_id INTEGER NOT NULL REFERENCES users(id), sender TEXT NOT NULL, body TEXT NOT NULL, created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS business_idempotency (
                user_id INTEGER NOT NULL, action TEXT NOT NULL, request_key TEXT NOT NULL, digest TEXT NOT NULL,
                response TEXT NOT NULL, created_at INTEGER NOT NULL, PRIMARY KEY(user_id, action, request_key)
            );
            SQL);
        $directory = $storage . '/business-files';
        if (!is_dir($directory) && !mkdir($directory, 0700)) {
            throw new RuntimeException('Private artwork storage is unavailable.');
        }
        if (realpath($directory) !== $directory || !is_writable($directory)) {
            throw new RuntimeException('Private artwork storage must not be symlinked.');
        }
    }

    public static function roles(array $config, array $user): array
    {
        // Numeric account IDs are assigned by the owner in private config; signup cannot grant a role.
        $roles = $config['staff_users'][(int)$user['id']] ?? [];
        return is_array($roles) ? array_values(array_intersect($roles, ['admin', 'sales', 'inventory', 'production', 'qc', 'fulfillment', 'support'])) : [];
    }

    private function staff(string ...$roles): void
    {
        if (!array_intersect(self::roles($this->config, $this->user), array_merge(['admin'], $roles))) {
            throw new PortalError('This action requires authorized team access.', 403);
        }
    }

    private function isStaff(): bool
    {
        return self::roles($this->config, $this->user) !== [];
    }

    private function rows(string $sql, array $args = []): array
    {
        $query = $this->db->prepare($sql);
        $query->execute($args);
        return $query->fetchAll();
    }

    private function exec(string $sql, array $args = []): void
    {
        $query = $this->db->prepare($sql);
        $query->execute($args);
    }

    private function text(mixed $value, int $max = 200, bool $optional = false): string
    {
        if (!is_string($value) || strlen(trim($value)) > $max || preg_match('/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/', $value)
            || (!$optional && trim($value) === '')) {
            throw new PortalError('Complete each required field within its length limit.', 422);
        }
        return trim($value);
    }

    private function integer(mixed $value, int $min, int $max): int
    {
        if (!is_int($value) || $value < $min || $value > $max) {
            throw new PortalError('Enter a number within the allowed range.', 422);
        }
        return $value;
    }

    private function quantity(mixed $value, bool $zero = false): int
    {
        if (!is_string($value) || !preg_match('/^[0-9]{1,7}(?:\.[0-9]{1,3})?$/D', $value)) {
            throw new PortalError('Use a quantity with up to three decimal places.', 422);
        }
        $parts = explode('.', $value);
        $amount = (int)$parts[0] * 1000 + (int)str_pad($parts[1] ?? '', 3, '0');
        if (!$zero && $amount === 0) {
            throw new PortalError('Quantity must be greater than zero.', 422);
        }
        return $amount;
    }

    private function order(mixed $id, bool $owner = false): array
    {
        if (!is_string($id) || !preg_match('/^MLED-[a-f0-9]{20}$/D', $id)) {
            throw new PortalError('This build request is unavailable.', 404);
        }
        $rows = $this->rows('SELECT * FROM business_orders WHERE id = ?', [$id]);
        $order = $rows[0] ?? null;
        if ($order === null || (($owner || !$this->isStaff()) && (int)$order['user_id'] !== (int)$this->user['id'])) {
            throw new PortalError('This build request is unavailable.', 404);
        }
        return $order;
    }

    private function revision(array $order, array $data, array $states): void
    {
        if (($data['revision'] ?? null) !== (int)$order['revision'] || !in_array($order['status'], $states, true)) {
            throw new PortalError('This build changed or is not ready for that step. Refresh its current status.', 409);
        }
    }

    private function update(array $order, array $values): void
    {
        $values['revision'] = (int)$order['revision'] + 1;
        $values['updated_at'] = time();
        $this->exec('UPDATE business_orders SET ' . implode(',', array_map(static fn($key) => $key . ' = ?', array_keys($values))) . ' WHERE id = ?', [...array_values($values), $order['id']]);
    }

    private function event(?string $order, string $kind, array $detail, ?string $customerMessage = null): void
    {
        $this->exec('INSERT INTO business_events(order_id,actor_id,kind,detail,customer_message,created_at) VALUES(?,?,?,?,?,?)',
            [$order, $this->user['id'], $kind, json_encode($detail, JSON_THROW_ON_ERROR), $customerMessage, time()]);
    }

    private function task(string $ref, string $kind, string $title): void
    {
        $this->exec("INSERT INTO business_tasks(reference,kind,title,created_at,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(reference,kind) DO UPDATE SET state='OPEN',note=NULL,updated_at=excluded.updated_at", [$ref, $kind, $title, time(), time()]);
    }

    private function closeTask(string $ref, string $kind): void
    {
        $this->exec("UPDATE business_tasks SET state='DONE',updated_at=? WHERE reference=? AND kind=?", [time(), $ref, $kind]);
    }

    public function handle(string $action, array $data): never
    {
        if (in_array($action, self::READS, true)) {
            $result = match ($action) {
                'business-orders' => ['orders' => $this->orders()],
                'business-tickets' => ['tickets' => $this->tickets()],
                'business-updates' => ['updates' => $this->rows('SELECT e.order_id,e.kind,e.customer_message,e.created_at FROM business_events e JOIN business_orders o ON o.id=e.order_id WHERE o.user_id=? AND e.customer_message IS NOT NULL ORDER BY e.id DESC LIMIT 100', [$this->user['id']])],
                'business-dashboard' => $this->dashboard(),
                'business-manifest' => $this->manifest(),
                'business-file' => $this->download(),
            };
            portal_json(['ok' => true] + $result);
        }
        $key = $data['requestKey'] ?? '';
        if (!is_string($key) || !preg_match('/^[A-Za-z0-9_-]{16,64}$/D', $key)) {
            throw new PortalError('A request reference is required. Refresh and try again.', 422);
        }
        unset($data['csrf']);
        if ($action === 'business-upload' && isset($_FILES['file']['tmp_name']) && is_string($_FILES['file']['tmp_name']) && is_uploaded_file($_FILES['file']['tmp_name'])) {
            $data['fileDigest'] = hash_file('sha256', $_FILES['file']['tmp_name']);
            $data['fileName'] = $_FILES['file']['name'] ?? '';
        }
        $digest = hash('sha256', json_encode($data, JSON_THROW_ON_ERROR));
        $this->db->exec('BEGIN IMMEDIATE');
        try {
            $saved = $this->rows('SELECT digest,response FROM business_idempotency WHERE user_id=? AND action=? AND request_key=?', [$this->user['id'], $action, $key]);
            if ($saved) {
                if (!hash_equals($saved[0]['digest'], $digest)) {
                    throw new PortalError('This request reference already belongs to different information.', 409);
                }
                $result = json_decode($saved[0]['response'], true, 32, JSON_THROW_ON_ERROR);
            } else {
                $result = match ($action) {
                    'business-request' => $this->request($data),
                    'business-upload' => $this->upload($data),
                    'business-proof' => $this->proof($data),
                    'business-approve' => $this->approve($data),
                    'business-receive' => $this->receive($data),
                    'business-reserve' => $this->reserve($data),
                    'business-release' => $this->release($data),
                    'business-build' => $this->build($data),
                    'business-qc' => $this->qc($data),
                    'business-fulfill' => $this->fulfill($data),
                    'business-cancel' => $this->cancel($data),
                    'business-ticket' => $this->ticket($data),
                    'business-reply' => $this->reply($data),
                    'business-task' => $this->taskAction($data),
                    default => throw new PortalError('This business action is unavailable.', 404),
                };
                $this->exec('INSERT INTO business_idempotency(user_id,action,request_key,digest,response,created_at) VALUES(?,?,?,?,?,?)', [$this->user['id'], $action, $key, $digest, json_encode($result, JSON_THROW_ON_ERROR), time()]);
            }
            $this->db->exec('COMMIT');
        } catch (Throwable $error) {
            $this->db->exec('ROLLBACK');
            foreach ($this->moved as $path) {
                if (is_file($path)) { unlink($path); }
            }
            throw $error;
        }
        portal_json(['ok' => true] + $result);
    }

    private function request(array $data): array
    {
        $items = $data['items'] ?? null;
        if (!is_array($items) || !array_is_list($items) || count($items) < 1 || count($items) > 20) {
            throw new PortalError('A build request needs between one and twenty items.', 422);
        }
        if ((int)($this->rows("SELECT COUNT(*) AS n FROM business_orders WHERE user_id=? AND status NOT IN ('COMPLETED','CANCELLED')", [$this->user['id']])[0]['n']) >= 50) {
            throw new PortalError('Please resolve existing requests before adding another build.', 409);
        }
        $catalog = ['Custom Infinity Mirror', 'Layered Stadium Model', 'Wall Panel LED Display', 'Address Sign or Mailbox', 'Other Custom Build'];
        $clean = [];
        foreach ($items as $item) {
            if (!is_array($item) || !in_array($item['product'] ?? null, $catalog, true)) {
                throw new PortalError('Choose a product from the website catalog.', 422);
            }
            $source = $item['artworkSource'] ?? 'team-design';
            if (!in_array($source, ['team-design', 'upload'], true)) {
                throw new PortalError('Choose uploaded artwork or a Mirroried LED team design.', 422);
            }
            $size = $this->text($item['size'] ?? null, 120);
            if ($item['product'] === 'Layered Stadium Model' && !in_array($size, ['Mini','Medium','Collector'], true)) {
                throw new PortalError('Stadium models are offered in Mini, Medium and Collector sizes.', 422);
            }
            $clean[] = ['product' => $item['product'], 'size' => $size, 'artwork' => $this->text($item['artwork'] ?? null, 1000),
                'artworkSource' => $source, 'lighting' => $this->text($item['lighting'] ?? '', 120, true),
                'finish' => $this->text($item['finish'] ?? '', 120, true), 'notes' => $this->text($item['notes'] ?? '', 2000, true),
                'quantity' => $this->integer($item['quantity'] ?? 1, 1, 20)];
            if (isset($item['builder'])) {
                if ($item['product'] !== 'Custom Infinity Mirror') { throw new PortalError('Infinity builder configuration requires an infinity mirror.', 422); }
                $builder = InfinityBuilder::validateConfiguration($item['builder'], $this->db, (int)$this->user['id']);
                if ($size !== implode('×', $builder['state']['size'])) { throw new PortalError('The mirror size does not match the builder configuration.', 422); }
                $clean[array_key_last($clean)]['builder'] = $builder;
            }
        }
        $id = 'MLED-' . bin2hex(random_bytes(10));
        $this->exec('INSERT INTO business_orders(id,user_id,configuration,created_at,updated_at) VALUES(?,?,?,?,?)', [$id, $this->user['id'], json_encode($clean, JSON_THROW_ON_ERROR), time(), time()]);
        $this->event($id, 'REQUESTED', ['items' => count($clean)], 'Your build request is saved for a quote review.');
        $this->task($id, 'QUOTE_REVIEW', 'Review configuration, artwork and pricing');
        return ['order' => $this->publicOrder($this->order($id, true))];
    }

    private function publicFile(array $row): array
    {
        return array_intersect_key($row, array_flip(['id', 'name', 'purpose', 'mime', 'bytes', 'sha256', 'created_at']))
            + ['url' => 'backend/api.php?action=business-file&id=' . rawurlencode($row['id'])];
    }

    private function publicOrder(array $order, bool $internal = false): array
    {
        $result = ['id' => $order['id'], 'status' => $order['status'], 'revision' => (int)$order['revision'],
            'items' => json_decode($order['configuration'], true, 16, JSON_THROW_ON_ERROR), 'quoteCents' => $order['quote_cents'] === null ? null : (int)$order['quote_cents'],
            'currency' => 'USD', 'approvedProofId' => $order['approved_proof_id'], 'scheduledAt' => $order['scheduled_at'],
            'carrier' => $order['carrier'], 'tracking' => $order['tracking'], 'createdAt' => (int)$order['created_at'], 'updatedAt' => (int)$order['updated_at'],
            'files' => array_map($this->publicFile(...), $this->rows('SELECT * FROM business_files WHERE order_id=? AND purpose<>? ORDER BY created_at', [$order['id'], $internal ? '' : 'production'])),
            'proof' => null,
            'timeline' => $this->rows('SELECT kind,customer_message,created_at FROM business_events WHERE order_id=? AND customer_message IS NOT NULL ORDER BY id', [$order['id']])];
        if ($order['proof_id'] !== null) {
            $proof = $this->rows('SELECT id,version,summary,file_id,quote_cents,created_at FROM business_proofs WHERE id=?', [$order['proof_id']]);
            $result['proof'] = $proof[0] ?? null;
        }
        if ($internal) {
            $customer = $this->rows('SELECT id,name,email FROM users WHERE id=?', [$order['user_id']])[0];
            $result += ['customer' => $customer, 'machine' => $order['machine'], 'financeReference' => $order['finance_reference'],
                'productionFileId' => $order['production_file_id'], 'qcNote' => $order['qc_note'],
                'reservations' => $this->rows('SELECT r.stock_id,r.quantity,s.name,s.sku,s.unit,s.lot FROM business_reservations r JOIN business_stock s ON s.id=r.stock_id WHERE r.order_id=?', [$order['id']])];
        }
        return $result;
    }

    private function orders(): array
    {
        return array_map($this->publicOrder(...), $this->rows('SELECT * FROM business_orders WHERE user_id=? ORDER BY created_at DESC,id DESC LIMIT 200', [$this->user['id']]));
    }

    private function upload(array $data): array
    {
        $purpose = $data['purpose'] ?? 'artwork';
        if (!in_array($purpose, ['artwork', 'proof', 'production'], true)) {
            throw new PortalError('Choose artwork, proof or production artwork.', 422);
        }
        if ($purpose !== 'artwork') { $this->staff('sales', 'production'); }
        $order = $this->order($data['orderId'] ?? null, $purpose === 'artwork');
        if (!in_array($order['status'], ['REQUESTED','QUOTED','APPROVED'], true)) {
            throw new PortalError('Files are locked after the build is released.', 409);
        }
        if ($purpose === 'artwork' && $order['status'] !== 'REQUESTED') {
            throw new PortalError('Request an artwork revision through support before changing a quoted build.', 409);
        }
        $file = $_FILES['file'] ?? null;
        if (!is_array($file) || !is_int($file['error'] ?? null) || $file['error'] !== UPLOAD_ERR_OK || !is_string($file['tmp_name'] ?? null) || !is_uploaded_file($file['tmp_name'])) {
            throw new PortalError('Choose a complete artwork file within the upload limit.', 422);
        }
        $name = basename(str_replace('\\', '/', $this->text($file['name'] ?? null, 200)));
        if (preg_match('/\.(?:php[0-9]?|phtml|phar|html?|js|exe|bat|cmd|sh)(?:\.|$)/i', $name)) {
            throw new PortalError('This artwork filename is not supported.', 422);
        }
        $ext = strtolower(pathinfo($name, PATHINFO_EXTENSION));
        $mime = (new finfo(FILEINFO_MIME_TYPE))->file($file['tmp_name']);
        $bytes = filesize($file['tmp_name']);
        $formats = ['png' => ['image/png'], 'jpg' => ['image/jpeg'], 'jpeg' => ['image/jpeg'], 'webp' => ['image/webp'], 'pdf' => ['application/pdf'], 'svg' => ['image/svg+xml','text/xml','application/xml','text/plain'], 'lbrn2' => ['text/xml','application/xml','text/plain']];
        if (!isset($formats[$ext]) || !in_array($mime, $formats[$ext], true) || ($ext === 'lbrn2' && $purpose !== 'production')
            || ($purpose === 'production' && !in_array($ext, ['svg', 'lbrn2'], true))
            || $bytes === false || $bytes < 1 || $bytes > 10485760 || $bytes !== (int)($file['size'] ?? -1)) {
            throw new PortalError('Upload a PNG, JPEG, PDF or SVG up to 10 MB. Team production files may also use LBRN2.', 422);
        }
        if (in_array($ext, ['png', 'jpg', 'jpeg', 'webp'], true) && @getimagesize($file['tmp_name']) === false) {
            throw new PortalError('This artwork image could not be verified.', 422);
        }
        if (in_array($ext, ['svg','lbrn2'], true)) {
            if (!extension_loaded('dom')) { throw new PortalError('XML artwork uploads need the server XML extension.', 503); }
            $xml = file_get_contents($file['tmp_name']);
            if ($xml === false || preg_match('/<!DOCTYPE|<!ENTITY/i', $xml)) { throw new PortalError('External XML definitions are not accepted.', 422); }
            $previous = libxml_use_internal_errors(true);
            $document = new DOMDocument();
            $valid = $document->loadXML($xml, LIBXML_NONET);
            libxml_clear_errors(); libxml_use_internal_errors($previous);
            if (!$valid || ($ext === 'svg' && $document->documentElement?->localName !== 'svg')
                || ($ext === 'lbrn2' && $document->documentElement?->localName !== 'LightBurnProject')) {
                throw new PortalError('This artwork XML could not be verified.', 422);
            }
            $mime = $ext === 'svg' ? 'image/svg+xml' : 'application/xml';
        }
        $usage = $this->rows('SELECT COUNT(*) AS n,COALESCE(SUM(bytes),0) AS bytes FROM business_files WHERE order_id=?', [$order['id']])[0];
        if ((int)$usage['n'] >= 20 || (int)$usage['bytes'] + $bytes > 52428800) {
            throw new PortalError('This build has reached its artwork storage limit. Contact the team.', 409);
        }
        $id = bin2hex(random_bytes(16)); $filename = $id . '.asset'; $path = $this->storage . '/business-files/' . $filename;
        $sha = hash_file('sha256', $file['tmp_name']);
        if (file_exists($path) || !move_uploaded_file($file['tmp_name'], $path)) { throw new RuntimeException('Private artwork could not be saved.'); }
        $this->moved[] = $path; chmod($path, 0600);
        $this->exec('INSERT INTO business_files(id,order_id,uploader_id,purpose,name,mime,bytes,sha256,filename,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)', [$id,$order['id'],$this->user['id'],$purpose,$name,$mime,$bytes,$sha,$filename,time()]);
        $this->event($order['id'], 'FILE_SAVED', ['fileId'=>$id,'purpose'=>$purpose], $purpose === 'artwork' ? 'Your artwork was saved privately.' : null);
        return ['file' => $this->publicFile($this->rows('SELECT * FROM business_files WHERE id=?', [$id])[0])];
    }

    private function download(): never
    {
        $id = $_GET['id'] ?? '';
        if (!is_string($id) || !preg_match('/^[a-f0-9]{32}$/D', $id)) { throw new PortalError('This file is unavailable.', 404); }
        $file = $this->rows('SELECT * FROM business_files WHERE id=?', [$id])[0] ?? null;
        if ($file === null) { throw new PortalError('This file is unavailable.', 404); }
        $this->order($file['order_id']);
        if ($file['purpose'] === 'production') { $this->staff('production'); }
        $path = $this->storage . '/business-files/' . $file['filename'];
        if (!preg_match('/^[a-f0-9]{32}\.asset$/D', $file['filename']) || realpath($path) !== $path || !is_file($path) || filesize($path) !== (int)$file['bytes']) {
            throw new PortalError('This file is unavailable.', 404);
        }
        session_write_close();
        header('Content-Type: ' . $file['mime']);
        header('Content-Length: ' . $file['bytes']);
        header('Content-Security-Policy: sandbox');
        header("Content-Disposition: attachment; filename=\"artwork\"; filename*=UTF-8''" . rawurlencode($file['name']));
        readfile($path); exit;
    }

    private function proof(array $data): array
    {
        $this->staff('sales'); $order = $this->order($data['orderId'] ?? null);
        $this->revision($order,$data,['REQUESTED','QUOTED','APPROVED']);
        $fileId = $this->text($data['fileId'] ?? null, 32);
        if (!$this->rows("SELECT id FROM business_files WHERE id=? AND order_id=? AND purpose='proof'", [$fileId,$order['id']])) { throw new PortalError('Attach a private proof file for this build first.', 422); }
        $amount = $this->integer($data['quoteCents'] ?? null, 0, 100000000);
        $summary = $this->text($data['summary'] ?? null, 4000);
        $version = (int)$this->rows('SELECT COALESCE(MAX(version),0)+1 AS n FROM business_proofs WHERE order_id=?',[$order['id']])[0]['n'];
        $id = bin2hex(random_bytes(16));
        $this->exec('INSERT INTO business_proofs(id,order_id,version,summary,file_id,quote_cents,creator_id,created_at) VALUES(?,?,?,?,?,?,?,?)',[$id,$order['id'],$version,$summary,$fileId,$amount,$this->user['id'],time()]);
        $this->update($order,['status'=>'QUOTED','quote_cents'=>$amount,'proof_id'=>$id,'approved_proof_id'=>null]);
        $this->closeTask($order['id'],'QUOTE_REVIEW');
        $this->event($order['id'],'QUOTED',['proofId'=>$id,'version'=>$version,'quoteCents'=>$amount],'A quote and artwork proof are ready for your review.');
        return ['order'=>$this->publicOrder($this->order($order['id']))];
    }

    private function approve(array $data): array
    {
        $order=$this->order($data['orderId']??null,true); $this->revision($order,$data,['QUOTED']);
        if (($data['proofId']??null)!==$order['proof_id'] || ($data['acceptQuote']??false)!==true) { throw new PortalError('Review the latest proof and quoted amount before approving.',422); }
        $this->update($order,['status'=>'APPROVED','approved_proof_id'=>$order['proof_id']]);
        $this->event($order['id'],'APPROVED',['proofId'=>$order['proof_id'],'quoteCents'=>$order['quote_cents']],'You approved this proof and quote. The team will check production readiness.');
        $this->task($order['id'],'RELEASE_REVIEW','Check materials, production file and financial release reference');
        return ['order'=>$this->publicOrder($this->order($order['id'],true))];
    }

    private function stock(): array
    {
        return $this->rows('SELECT s.*,COALESCE((SELECT SUM(r.quantity) FROM business_reservations r WHERE r.stock_id=s.id),0) AS reserved FROM business_stock s ORDER BY s.name,s.lot LIMIT 500');
    }

    private function receive(array $data): array
    {
        $this->staff('inventory');
        $sku=$this->text($data['sku']??null,80); $name=$this->text($data['name']??null,120); $lot=$this->text($data['lot']??null,80);
        $location=$this->text($data['location']??null,120);$unit=$this->text($data['unit']??null,40); $qty=$this->quantity($data['quantity']??null);
        $threshold=$this->quantity($data['threshold']??'0',true); $cost=$this->integer($data['costCents']??null,0,10000000);
        $quality=$data['quality']??null; if(!in_array($quality,['PASSED','QUARANTINED'],true)){throw new PortalError('Record incoming inspection as passed or quarantined.',422);}
        $stock=$this->rows('SELECT * FROM business_stock WHERE sku=? AND lot=?',[$sku,$lot])[0]??null;
        if($stock!==null){
            foreach(['name'=>$name,'location'=>$location,'unit'=>$unit,'quality'=>$quality,'cost_cents'=>$cost,'threshold'=>$threshold] as $k=>$v){if((string)$stock[$k] !== (string)$v){throw new PortalError('Existing lots keep their original traceability data. Use a new lot for a changed receipt.',409);}}
            $id=(int)$stock['id'];$this->exec('UPDATE business_stock SET quantity=quantity+? WHERE id=?',[$qty,$id]);
        }else{
            $this->exec('INSERT INTO business_stock(sku,name,lot,location,unit,quantity,threshold,cost_cents,quality) VALUES(?,?,?,?,?,?,?,?,?)',[$sku,$name,$lot,$location,$unit,$qty,$threshold,$cost,$quality]);$id=(int)$this->db->lastInsertId();
        }
        $this->exec("INSERT INTO business_movements(stock_id,kind,quantity,cost_cents,actor_id,created_at) VALUES(?,'RECEIPT',?,?,?,?)",[$id,$qty,$cost,$this->user['id'],time()]);
        $this->event(null,'STOCK_RECEIVED',['stockId'=>$id,'quantity'=>$qty,'quality'=>$quality]);
        $this->lowStock(); return ['stock'=>$this->stock()];
    }

    private function reserve(array $data): array
    {
        $this->staff('inventory','production');$order=$this->order($data['orderId']??null);$this->revision($order,$data,['REQUESTED','QUOTED','APPROVED']);
        $stockId=$this->integer($data['stockId']??null,1,PHP_INT_MAX);$qty=$this->quantity($data['quantity']??null);
        $stock=$this->rows('SELECT * FROM business_stock WHERE id=?',[$stockId])[0]??null;
        if($stock===null||$stock['quality']!=='PASSED'){throw new PortalError('Only a known, inspected material lot can be reserved.',409);}
        $reserved=(int)$this->rows('SELECT COALESCE(SUM(quantity),0) AS n FROM business_reservations WHERE stock_id=? AND order_id<>?',[$stockId,$order['id']])[0]['n'];
        if($qty>(int)$stock['quantity']-$reserved){throw new PortalError('There is not enough available stock for this reservation.',409);}
        $this->exec('INSERT INTO business_reservations(order_id,stock_id,quantity) VALUES(?,?,?) ON CONFLICT(order_id,stock_id) DO UPDATE SET quantity=excluded.quantity',[$order['id'],$stockId,$qty]);
        $this->update($order,[]);$this->event($order['id'],'MATERIAL_RESERVED',['stockId'=>$stockId,'quantity'=>$qty]);$this->lowStock();
        return ['order'=>$this->publicOrder($this->order($order['id']),true)];
    }

    private function lowStock(): void
    {
        foreach($this->stock() as $s){
            if($s['quality']==='PASSED'&&(int)$s['quantity']-(int)$s['reserved']<=(int)$s['threshold']){$this->task('STOCK-'.$s['id'],'REPLENISH','Review replenishment for '.$s['name']);}
            else{$this->closeTask('STOCK-'.$s['id'],'REPLENISH');}
        }
    }

    private function release(array $data): array
    {
        $this->staff('production');$order=$this->order($data['orderId']??null);$this->revision($order,$data,['APPROVED']);
        if($order['approved_proof_id']===null||$order['approved_proof_id']!==$order['proof_id']||($data['materialsComplete']??false)!==true||($data['assetReviewed']??false)!==true){throw new PortalError('Current proof approval, complete materials and a reviewed production file are required.',409);}
        $fileId=$this->text($data['fileId']??null,32);
        if(!$this->rows("SELECT id FROM business_files WHERE id=? AND order_id=? AND purpose='production'",[$fileId,$order['id']])){throw new PortalError('Choose the reviewed production file for this build.',422);}
        $materials=$this->rows('SELECT r.*,s.quantity AS stock_quantity,s.quality FROM business_reservations r JOIN business_stock s ON s.id=r.stock_id WHERE r.order_id=?',[$order['id']]);
        if(!$materials){throw new PortalError('Reserve the approved bill of materials before release.',409);}
        foreach($materials as $m){$total=(int)$this->rows('SELECT SUM(quantity) AS n FROM business_reservations WHERE stock_id=?',[$m['stock_id']])[0]['n'];if($m['quality']!=='PASSED'||$total>(int)$m['stock_quantity']){throw new PortalError('Material readiness needs review.',409);}}
        $reference=$this->text($data['financeReference']??null,200);$machine=$this->text($data['machine']??null,100);
        $start=$this->integer($data['scheduledAt']??null,time()-300,time()+31536000);$minutes=$this->integer($data['minutes']??null,1,1440);$end=$start+$minutes*60;
        if($this->rows("SELECT id FROM business_orders WHERE machine=? AND status IN ('READY','BUILDING','QC_HOLD') AND scheduled_at < ? AND scheduled_end > ?",[$machine,$end,$start])){throw new PortalError('That production resource already has work in this time slot.',409);}
        $this->update($order,['status'=>'READY','production_file_id'=>$fileId,'finance_reference'=>$reference,'machine'=>$machine,'scheduled_at'=>$start,'scheduled_end'=>$end]);
        $this->closeTask($order['id'],'RELEASE_REVIEW');$this->task($order['id'],'PRODUCTION','Prepare the released job on the local shop computer');
        $this->event($order['id'],'READY',['fileId'=>$fileId,'financeReference'=>$reference,'machine'=>$machine,'scheduledAt'=>$start],'Your build is ready for the scheduled production step.');
        return ['order'=>$this->publicOrder($this->order($order['id']),true),'physicalExecution'=>false];
    }

    private function build(array $data): array
    {
        $this->staff('production');$order=$this->order($data['orderId']??null);$this->revision($order,$data,['READY']);
        $materials=$this->rows('SELECT r.*,s.quantity AS stock_quantity,s.cost_cents,s.quality FROM business_reservations r JOIN business_stock s ON s.id=r.stock_id WHERE r.order_id=?',[$order['id']]);
        if(!$materials){throw new PortalError('Reserved materials are required.',409);}
        foreach($materials as $m){
            if($m['quality']!=='PASSED'||(int)$m['quantity']>(int)$m['stock_quantity']){throw new PortalError('Reserved materials are unavailable.',409);}
            $this->exec('UPDATE business_stock SET quantity=quantity-? WHERE id=?',[$m['quantity'],$m['stock_id']]);
            $this->exec("INSERT INTO business_movements(stock_id,order_id,kind,quantity,cost_cents,actor_id,created_at) VALUES(?,?,'CONSUMED',?,?,?,?)",[$m['stock_id'],$order['id'],$m['quantity'],$m['cost_cents'],$this->user['id'],time()]);
        }
        $this->exec('DELETE FROM business_reservations WHERE order_id=?',[$order['id']]);$this->update($order,['status'=>'BUILDING']);
        $this->event($order['id'],'BUILDING',['materials'=>count($materials)],'The team recorded the start of your build.');$this->lowStock();
        return ['order'=>$this->publicOrder($this->order($order['id']),true),'physicalExecution'=>false];
    }

    private function qc(array $data): array
    {
        $this->staff('qc');$order=$this->order($data['orderId']??null);$this->revision($order,$data,['BUILDING','QC_HOLD']);
        $pass=($data['passed']??null);if(!is_bool($pass)){throw new PortalError('Record a pass or hold inspection result.',422);}
        $note=$this->text($data['note']??null,2000);
        if($pass){foreach(['dimensions','finish','electrical','function'] as $check){if(($data['checks'][$check]??false)!==true){throw new PortalError('Complete dimensions, finish, electrical and function inspection before passing QC.',409);}}}
        $state=$pass?'QC_PASSED':'QC_HOLD';$this->update($order,['status'=>$state,'qc_note'=>$note]);
        $this->event($order['id'],$state,['note'=>$note,'checks'=>$data['checks']??[]],$pass?'Your build passed its recorded quality inspection.':'Your build is on a quality hold while the team resolves an issue.');
        if($pass){$this->closeTask($order['id'],'QC_REVIEW');$this->closeTask($order['id'],'PRODUCTION');$this->task($order['id'],'FULFILLMENT','Pack and confirm pickup or shipping details');}
        else{$this->task($order['id'],'QC_REVIEW','Resolve the nonconformance and reinspect');}
        return ['order'=>$this->publicOrder($this->order($order['id']),true)];
    }

    private function fulfill(array $data): array
    {
        $this->staff('fulfillment');$order=$this->order($data['orderId']??null);
        $complete=($data['complete']??false)===true;$this->revision($order,$data,$complete?['FULFILLING']:['QC_PASSED']);
        $carrier=$this->text($data['carrier']??null,100);$tracking=$this->text($data['tracking']??null,200);$note=$this->text($data['note']??null,1000);
        $state=$complete?'COMPLETED':'FULFILLING';$this->update($order,['status'=>$state,'carrier'=>$carrier,'tracking'=>$tracking]);
        $this->event($order['id'],$state,['carrier'=>$carrier,'tracking'=>$tracking,'note'=>$note],$complete?'The team recorded completed delivery or pickup.':'Pickup or shipment details have been recorded for your build.');
        if($complete){$this->closeTask($order['id'],'FULFILLMENT');}
        return ['order'=>$this->publicOrder($this->order($order['id']),true)];
    }

    private function cancel(array $data): array
    {
        $this->staff('sales','production');$order=$this->order($data['orderId']??null);$this->revision($order,$data,['REQUESTED','QUOTED','APPROVED','READY']);
        $note=$this->text($data['note']??null,2000);$this->exec('DELETE FROM business_reservations WHERE order_id=?',[$order['id']]);$this->update($order,['status'=>'CANCELLED']);
        $this->exec("UPDATE business_tasks SET state='DONE',updated_at=? WHERE reference=?",[time(),$order['id']]);$this->lowStock();
        $this->event($order['id'],'CANCELLED',['note'=>$note],'The team cancelled this request. Contact support for its recorded resolution.');
        return ['order'=>$this->publicOrder($this->order($order['id']),true)];
    }

    private function tickets(bool $internal=false): array
    {
        $rows=$this->rows('SELECT * FROM business_tickets '.($internal?'':'WHERE user_id=? ').'ORDER BY created_at DESC,id DESC LIMIT 200',$internal?[]:[$this->user['id']]);
        foreach($rows as &$ticket){$ticket['messages']=$this->rows('SELECT sender,body,created_at FROM business_messages WHERE ticket_id=? ORDER BY id',[$ticket['id']]);}
        return $rows;
    }

    private function ticket(array $data): array
    {
        $kind=$data['kind']??'SUPPORT';if(!in_array($kind,['SUPPORT','WARRANTY','RETURN','ORDER','LED_SETUP'],true)){throw new PortalError('Choose a supported request type.',422);}
        $orderId=$data['orderId']??null;if($orderId!==null&&$orderId!==''){$orderId=$this->order($orderId,true)['id'];}else{$orderId=null;}
        if(count($this->rows("SELECT id FROM business_tickets WHERE user_id=? AND state='OPEN' LIMIT 51",[$this->user['id']]))>=50){throw new PortalError('Please resolve open support requests before adding another.',409);}
        $id='TICKET-'.bin2hex(random_bytes(10));$subject=$this->text($data['subject']??null,200);$body=$this->text($data['body']??null,4000);
        $this->exec('INSERT INTO business_tickets(id,user_id,order_id,kind,subject,created_at) VALUES(?,?,?,?,?,?)',[$id,$this->user['id'],$orderId,$kind,$subject,time()]);
        $this->exec("INSERT INTO business_messages(ticket_id,actor_id,sender,body,created_at) VALUES(?,?,'CUSTOMER',?,?)",[$id,$this->user['id'],$body,time()]);
        $this->task($id,'SUPPORT','Review '.$kind.' request: '.$subject);$this->event($orderId,'SUPPORT_CREATED',['ticketId'=>$id,'kind'=>$kind]);return ['ticketId'=>$id];
    }

    private function reply(array $data): array
    {
        $id=$this->text($data['ticketId']??null,40);$ticket=$this->rows('SELECT * FROM business_tickets WHERE id=?',[$id])[0]??null;
        if($ticket===null){throw new PortalError('This support request is unavailable.',404);}
        $team=(int)$ticket['user_id']!==(int)$this->user['id'];if($team){$this->staff('support');}
        $body=$this->text($data['body']??null,4000);$close=($data['close']??false)===true;if($close){$this->staff('support');}
        $this->exec('INSERT INTO business_messages(ticket_id,actor_id,sender,body,created_at) VALUES(?,?,?,?,?)',[$id,$this->user['id'],$team?'TEAM':'CUSTOMER',$body,time()]);
        $this->exec('UPDATE business_tickets SET state=? WHERE id=?',[$close?'CLOSED':'OPEN',$id]);
        if($close){$this->closeTask($id,'SUPPORT');}else{$this->task($id,'SUPPORT','Review support reply: '.$ticket['subject']);}
        $this->event($ticket['order_id'],'SUPPORT_REPLY',['ticketId'=>$id,'closed'=>$close]);return ['ticketId'=>$id];
    }

    private function taskAction(array $data): array
    {
        $this->staff('sales','inventory','production','qc','fulfillment','support');$id=$this->integer($data['taskId']??null,1,PHP_INT_MAX);$note=$this->text($data['note']??null,1000);
        if(!$this->rows('SELECT id FROM business_tasks WHERE id=?',[$id])){throw new PortalError('This task is unavailable.',404);}
        $this->exec("UPDATE business_tasks SET state='DONE',note=?,updated_at=? WHERE id=?",[$note,time(),$id]);$this->event(null,'TASK_DONE',['taskId'=>$id,'note'=>$note]);return ['taskId'=>$id];
    }

    private function dashboard(): array
    {
        $this->staff('sales','inventory','production','qc','fulfillment','support');
        $orders=array_map(fn($o)=>$this->publicOrder($o,true),$this->rows('SELECT * FROM business_orders ORDER BY created_at DESC,id DESC LIMIT 200'));
        return ['orders'=>$orders,'stock'=>$this->stock(),'tickets'=>$this->tickets(true),
            'tasks'=>$this->rows('SELECT * FROM business_tasks ORDER BY state,created_at LIMIT 500'),
            'audit'=>$this->rows('SELECT * FROM business_events ORDER BY id DESC LIMIT 100'),
            'summary'=>$this->rows('SELECT status,COUNT(*) AS count FROM business_orders GROUP BY status'),
            'integrations'=>['payments'=>'Not connected','emailSms'=>'Not connected; portal updates only','shipping'=>'Team recorded references','laser'=>'Local operator handoff only','wled'=>'Local Chataigne / WLED-MM setup required']];
    }

    private function manifest(): array
    {
        $this->staff('production');$order=$this->order($_GET['orderId']??null);$public=$this->publicOrder($order,true);
        $moves=$this->rows("SELECT m.stock_id,m.quantity,m.cost_cents,s.sku,s.name,s.lot,s.unit FROM business_movements m JOIN business_stock s ON s.id=m.stock_id WHERE m.order_id=? AND m.kind='CONSUMED'",[$order['id']]);
        return ['manifest'=>['order'=>$public,'consumedMaterials'=>$moves,'physicalExecution'=>false,'operatorReviewRequired'=>true,'generatedAt'=>gmdate('c')]];
    }
}
