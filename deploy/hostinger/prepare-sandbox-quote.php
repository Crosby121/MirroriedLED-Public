<?php
declare(strict_types=1);
ini_set('display_errors', '0');
set_error_handler(static function (): never { throw new RuntimeException('Sandbox prerequisite unavailable'); });

/* CLI-only operator action. Never install this helper under public_html. */
function sandbox_quote_path(string $path, bool $directory, bool $private = false): void
{
    clearstatcache(true, $path);
    for ($ancestor = $path; $ancestor !== dirname($ancestor); $ancestor = dirname($ancestor)) {
        if (is_link($ancestor)) { throw new RuntimeException('Unsafe sandbox path'); }
    }
    $info = lstat($path);
    if (!$info || ($directory ? !is_dir($path) : !is_file($path))
        || $info['uid'] !== posix_geteuid() || ($info['mode'] & ($private ? 0077 : 0022)) !== 0
        || (!$directory && $info['nlink'] !== 1)) {
        throw new RuntimeException('Unsafe sandbox ownership or permissions');
    }
}

function sandbox_quote(string $root, string $fingerprint): array
{
    if (PHP_SAPI !== 'cli' || !preg_match('/^[a-f0-9]{64}$/D', $fingerprint)
        || basename($root) !== 'public_html' || basename(dirname($root)) !== 'mirroriedled.com'
        || realpath($root) !== $root) { throw new RuntimeException('Isolated sandbox required'); }
    sandbox_quote_path($root, true);
    sandbox_quote_path(dirname($root), true);
    $private = dirname($root) . '/mirroriedled-private/checkout-sandbox';
    sandbox_quote_path(dirname($private), true);
    sandbox_quote_path($private, true, true);
    sandbox_quote_path($private . '/config.php', false, true);
    sandbox_quote_path($private . '/receipt.json', false, true);
    $lockPath = $private . '/.quote-prepare.lock';
    if (file_exists($lockPath) || is_link($lockPath)) { sandbox_quote_path($lockPath, false, true); }
    $mask = umask(0077);
    try { $lock = fopen($lockPath, 'c+b'); } finally { umask($mask); }
    if (!$lock) { throw new RuntimeException('Sandbox lock unavailable'); }
    try {
        sandbox_quote_path($lockPath, false, true);
        if (fstat($lock)['ino'] !== lstat($lockPath)['ino'] || !flock($lock, LOCK_EX)) {
            throw new RuntimeException('Sandbox lock unavailable');
        }
        $receipt = json_decode(file_get_contents($private . '/receipt.json'), true, 32, JSON_THROW_ON_ERROR);
        if (($receipt['payments_enabled'] ?? null) !== false || !preg_match('/^[a-f0-9]{40}$/D', $receipt['source_sha'] ?? '')) {
            throw new RuntimeException('Disabled sandbox receipt required');
        }
        $backend = $root . '/MLED_checkout_TEST/customer-portal/backend';
        sandbox_quote_path($backend . '/api.php', false);
        $api = file_get_contents($backend . '/api.php');
        if (!str_contains($api, '/mirroriedled-private/checkout-sandbox/config.php')
            || !str_contains($api, 'X-MLED-Sandbox-Source: ' . $receipt['source_sha'])) {
            throw new RuntimeException('Sandbox API scope required');
        }
        $config = require $private . '/config.php';
        $commerce = $config['commerce'] ?? [];
        if (($commerce['enabled'] ?? null) !== false || ($commerce['mode'] ?? '') !== 'test'
            || !preg_match('/^rk_test_[A-Za-z0-9]+$/D', $commerce['stripe_secret_key'] ?? '')
            || ($config['storage_path'] ?? '') !== $private . '/storage'
            || ($config['staff_users'] ?? null) !== [] || ($config['premium_enabled'] ?? null) !== false) {
            throw new RuntimeException('Unchanged disabled sandbox configuration required');
        }
        $storage = $config['storage_path'];
        sandbox_quote_path($storage, true, true);
        sandbox_quote_path($storage . '/business-files', true, true);
        sandbox_quote_path($storage . '/portal.sqlite', false, true);
        $db = new PDO('sqlite:' . $storage . '/portal.sqlite', null, null,
            [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION, PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC]);
        $db->exec('PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000;');
        $matches = array_values(array_filter($db->query('SELECT * FROM business_orders')->fetchAll(),
            fn($order) => hash_equals($fingerprint, hash('sha256', $order['id']))));
        if (count($matches) !== 1) { throw new RuntimeException('Selected order not found'); }
        $order = $matches[0];
        $items = json_decode($order['configuration'], true, 32, JSON_THROW_ON_ERROR);
        if (count($items) !== 1 || ($items[0]['product'] ?? '') !== 'Custom Infinity Mirror'
            || ($items[0]['size'] ?? '') !== '12×12' || ($items[0]['quantity'] ?? null) !== 1) {
            throw new RuntimeException('Selected 12-inch test build required');
        }
        $query = $db->prepare('SELECT * FROM users WHERE id=?'); $query->execute([$order['user_id']]);
        $user = $query->fetch();
        if (!$user) { throw new RuntimeException('Order owner required'); }
        require_once $backend . '/portal.php';
        CommercePortal::migrate($db);
        if (CommercePortal::locked($db, $order['id'])) { throw new RuntimeException('Existing checkout preserved'); }
        $terms = CommercePortal::publicTerms($db, $order['id']);
        if (!$terms['address'] || ($terms['address']['country'] ?? '') !== 'US' || ($terms['address']['state'] ?? '') !== 'CA') {
            throw new RuntimeException('Saved California sandbox delivery address required');
        }
        // Ephemeral operator authority in this trusted CLI process only. No account/config role is saved.
        $config['staff_users'] = [(int)$user['id'] => ['sales']];
        $business = new BusinessPortal($db, $config, $storage, $user);
        $summary = 'SANDBOX CHECKOUT TEST ONLY: uploaded artwork reference, not a production-ready proof. '
            . 'Test product price $1.00 plus test tax; test shipping $0.00. No fabrication or shipping. '
            . 'The displayed production/transit estimates are artificial test terms.';
        if ($order['proof_id'] === null) {
            if ($order['status'] !== 'REQUESTED') { throw new RuntimeException('Existing quote preserved'); }
            $query = $db->prepare("SELECT * FROM business_files WHERE order_id=? AND purpose='artwork' ORDER BY created_at DESC, id DESC LIMIT 1");
            $query->execute([$order['id']]); $art = $query->fetch();
            if (!$art || !preg_match('/^[a-f0-9]{32}\.asset$/D', $art['filename'])) { throw new RuntimeException('Uploaded artwork required'); }
            $source = $storage . '/business-files/' . $art['filename'];
            sandbox_quote_path($source, false, true);
            if (filesize($source) !== (int)$art['bytes'] || !hash_equals($art['sha256'], hash_file('sha256', $source))) {
                throw new RuntimeException('Artwork integrity required');
            }
            $fileId = substr(hash('sha256', 'sandbox-proof-' . $order['id']), 0, 32);
            $destination = $storage . '/business-files/' . $fileId . '.asset';
            $db->exec('BEGIN IMMEDIATE');
            try {
                if (!file_exists($destination) && !is_link($destination)) {
                    $temporary = $storage . '/business-files/.sandbox-proof-' . bin2hex(random_bytes(16));
                    try {
                        $mask = umask(0077);
                        try { $output = fopen($temporary, 'xb'); } finally { umask($mask); }
                        if (!$output) { throw new RuntimeException('Private proof unavailable'); }
                        try {
                            $input = fopen($source, 'rb');
                            if (!$input) { throw new RuntimeException('Private artwork unavailable'); }
                            try { stream_copy_to_stream($input, $output); } finally { fclose($input); }
                            fflush($output);
                            fsync($output);
                        } finally { fclose($output); }
                        // All cooperating writers hold the same process lock. Publish a
                        // complete file in one rename so interruption cannot leave two links.
                        clearstatcache(true, $destination);
                        if (!hash_equals($art['sha256'], hash_file('sha256', $temporary))
                            || file_exists($destination) || is_link($destination) || !rename($temporary, $destination)) {
                            throw new RuntimeException('Private proof publication failed');
                        }
                    } finally { if (isset($temporary) && file_exists($temporary)) { unlink($temporary); } }
                }
                sandbox_quote_path($destination, false, true);
                if (!hash_equals($art['sha256'], hash_file('sha256', $destination))) { throw new RuntimeException('Existing proof file preserved'); }
                $query = $db->prepare('INSERT OR IGNORE INTO business_files(id,order_id,uploader_id,purpose,name,mime,bytes,sha256,filename,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)');
                $query->execute([$fileId,$order['id'],$user['id'],'proof','SANDBOX-TEST-artwork-reference',$art['mime'],$art['bytes'],$art['sha256'],$fileId.'.asset',time()]);
                $method = new ReflectionMethod(BusinessPortal::class, 'proof');
                $result = $method->invoke($business, ['orderId'=>$order['id'],'revision'=>(int)$order['revision'],
                    'fileId'=>$fileId,'quoteCents'=>100,'summary'=>$summary]);
                $order['proof_id'] = $result['order']['proof']['id'];
                $db->exec('COMMIT');
            } catch (Throwable $error) { $db->exec('ROLLBACK'); throw $error; }
        } else {
            $query = $db->prepare('SELECT summary,quote_cents FROM business_proofs WHERE id=? AND order_id=?');
            $query->execute([$order['proof_id'],$order['id']]); $proof = $query->fetch();
            if (!$proof || $proof['summary'] !== $summary || (int)$proof['quote_cents'] !== 100
                || !in_array($order['status'], ['QUOTED','APPROVED'], true)) { throw new RuntimeException('Existing proof preserved'); }
        }
        $terms = CommercePortal::publicTerms($db, $order['id']);
        if ($terms['offer'] === null) {
            $service = new CommercePortal($db, $config, $user);
            $method = new ReflectionMethod(CommercePortal::class, 'offer');
            $method->invoke($service, ['orderId'=>$order['id'],'proofId'=>$order['proof_id'], 'shippingCents'=>0,
                'productionMinDays'=>1,'productionMaxDays'=>2,'transitMinDays'=>1,'transitMaxDays'=>2,'fulfillmentConfirmed'=>true]);
        } elseif ($terms['offer']['proofId'] !== $order['proof_id'] || $terms['offer']['productCents'] !== 100
            || $terms['offer']['shippingCents'] !== 0) { throw new RuntimeException('Existing offer preserved'); }
        return ['order_located'=>true,'proof_ready'=>true,'product_cents'=>100,'shipping_cents'=>0,
            'customer_approval_required'=>true,'payments_enabled'=>false,'staff_roles_persisted'=>false,'production_files_changed'=>false];
    } finally { fclose($lock); }
}

try {
    if ($argc !== 3) { throw new RuntimeException('Required CLI arguments missing'); }
    echo json_encode(sandbox_quote($argv[1], $argv[2]), JSON_THROW_ON_ERROR) . PHP_EOL;
} catch (Throwable $error) {
    fwrite(STDERR, "Sandbox test quote preparation stopped; inspect private prerequisites. No live activation performed.\n");
    exit(1);
}
