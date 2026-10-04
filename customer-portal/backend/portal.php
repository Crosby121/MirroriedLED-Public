<?php
declare(strict_types=1);

require_once __DIR__ . '/business.php';
require_once __DIR__ . '/builder.php';

final class PortalError extends RuntimeException
{
    public function __construct(string $message, public readonly int $httpStatus = 400)
    {
        parent::__construct($message);
    }
}

function portal_json(array $data, int $status = 200): never
{
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($data, JSON_UNESCAPED_SLASHES | JSON_INVALID_UTF8_SUBSTITUTE | JSON_THROW_ON_ERROR);
    exit;
}

final class CustomerPortal
{
    private const PLAN_NAMES = ['free' => 'Free', 'premium' => 'Premium', 'premium-plus' => 'Premium+'];
    private array $config = [];
    private array $plans;
    private ?PDO $database = null;
    private bool $configured = false;
    private string $storage = '';
    private string $status = 'Private server setup is required before accounts and uploads can be enabled.';

    public function __construct()
    {
        $this->plans = [
            'free' => ['songs' => 3, 'videos' => 1, 'bytes' => 268435456],
            'premium' => ['songs' => 25, 'videos' => 5, 'bytes' => 2147483648],
            'premium-plus' => ['songs' => 100, 'videos' => 20, 'bytes' => 8589934592],
        ];
        try {
            $this->configure();
        } catch (Throwable $error) {
            // Public status never reveals filesystem locations or server details.
            error_log('Mirroried LED customer portal private configuration unavailable: ' . get_class($error));
            $this->configured = false;
            $this->database = null;
        }
    }

    public function handle(): never
    {
        $action = (string)($_GET['action'] ?? 'session');
        $method = strtoupper((string)($_SERVER['REQUEST_METHOD'] ?? 'GET'));
        $reads = array_merge(['session', 'library', 'media'], BusinessPortal::READS, InfinityBuilder::READS);
        $writes = array_merge(['signup', 'login', 'logout', 'upload', 'delete'], BusinessPortal::WRITES, InfinityBuilder::WRITES);
        if (!in_array($action, array_merge($reads, $writes), true)) {
            throw new PortalError('That portal action is unavailable.', 404);
        }
        if (($method !== 'GET' || !in_array($action, $reads, true))
            && ($method !== 'POST' || !in_array($action, $writes, true))) {
            header('Allow: ' . (in_array($action, $reads, true) ? 'GET' : 'POST'));
            throw new PortalError('Use the supported request method.', 405);
        }
        if ($action === 'session') {
            portal_json($this->sessionData());
        }
        if (!$this->configured) {
            throw new PortalError($this->status, 503);
        }
        $data = [];
        if (in_array($action, $writes, true)) {
            $data = in_array($action, ['upload', 'business-upload'], true) ? $_POST : $this->readJson($action === 'business-request' ? 131072 : 16384);
            $this->requireCsrf($data);
        }
        if (str_starts_with($action, 'business-')) {
            $business = new BusinessPortal($this->database, $this->config, $this->storage, $this->requireUser());
            $business->handle($action, $data);
        }
        if (str_starts_with($action, 'builder-')) {
            $builder = new InfinityBuilder($this->database, $this->config, $this->storage, $this->requireUser());
            $builder->handle($action, $data);
        }
        match ($action) {
            'signup' => $this->signup($data),
            'login' => $this->login($data),
            'logout' => $this->logout(),
            'library' => $this->library(),
            'upload' => $this->upload(),
            'delete' => $this->delete($data),
            'media' => $this->media(),
            default => throw new PortalError('That portal action is unavailable.', 404),
        };
        throw new LogicException('Portal action did not send a response.');
    }

    private function configure(): void
    {
        $documentRoot = realpath((string)($_SERVER['DOCUMENT_ROOT'] ?? ''));
        if ($documentRoot === false || $documentRoot === DIRECTORY_SEPARATOR) {
            throw new RuntimeException('A valid document root is required.');
        }
        $configuredPath = getenv('MLED_PORTAL_CONFIG');
        $configPath = realpath($configuredPath ?: dirname($documentRoot) . '/mirroriedled-private/customer-portal/config.php');
        if ($configPath === false || !is_file($configPath) || !is_readable($configPath)
            || $this->isWithin($configPath, $documentRoot)) {
            throw new RuntimeException('A private configuration file is required.');
        }
        $config = require $configPath;
        if (!is_array($config)) {
            throw new RuntimeException('Configuration must return an array.');
        }
        $https = in_array(strtolower((string)($_SERVER['HTTPS'] ?? '')), ['on', '1'], true)
            || (string)($_SERVER['SERVER_PORT'] ?? '') === '443';
        $hostname = strtolower((string)parse_url('http://' . (string)($_SERVER['HTTP_HOST'] ?? ''), PHP_URL_HOST));
        $localhost = in_array($hostname, ['localhost', '127.0.0.1', '[::1]'], true)
            && in_array((string)($_SERVER['REMOTE_ADDR'] ?? ''), ['127.0.0.1', '::1'], true);
        if (!$https && !(($config['allow_insecure_localhost'] ?? false) === true && $localhost)) {
            throw new RuntimeException('HTTPS is required.');
        }
        $origin = (string)($config['origin'] ?? '');
        if (!preg_match('~^https://[^/?#]+$~D', $origin)
            && !($localhost && ($config['allow_insecure_localhost'] ?? false) === true
                && preg_match('~^http://(?:127\.0\.0\.1|localhost|\[::1\])(?::[0-9]+)?$~D', $origin))) {
            throw new RuntimeException('An exact HTTPS origin is required.');
        }
        if (!extension_loaded('pdo_sqlite') || !extension_loaded('fileinfo')) {
            throw new RuntimeException('SQLite and fileinfo are required.');
        }
        $rawStorage = (string)($config['storage_path'] ?? '');
        if ($rawStorage === '' || $rawStorage[0] !== DIRECTORY_SEPARATOR) {
            throw new RuntimeException('An absolute private storage path is required.');
        }
        // Check the nearest existing ancestor before creating any storage directory.
        $ancestor = $rawStorage;
        while (!file_exists($ancestor) && dirname($ancestor) !== $ancestor) {
            $ancestor = dirname($ancestor);
        }
        $realAncestor = realpath($ancestor);
        if ($realAncestor === false || $this->isWithin($realAncestor, $documentRoot)) {
            throw new RuntimeException('Storage cannot be inside the document root.');
        }
        umask(0077);
        if (!is_dir($rawStorage) && !mkdir($rawStorage, 0700, true)) {
            throw new RuntimeException('Private storage could not be created.');
        }
        $storage = realpath($rawStorage);
        if ($storage === false || $this->isWithin($storage, $documentRoot) || !is_writable($storage)) {
            throw new RuntimeException('Private storage is unavailable.');
        }
        chmod($storage, 0700);
        foreach (['media', 'sessions'] as $directory) {
            $path = $storage . '/' . $directory;
            if (!is_dir($path) && !mkdir($path, 0700)) {
                throw new RuntimeException('Private storage directory could not be created.');
            }
            $real = realpath($path);
            if ($real !== $path || !is_writable($path)) {
                throw new RuntimeException('Private storage symlinks are not allowed.');
            }
            chmod($path, 0700);
        }
        foreach ($this->plans as $id => $default) {
            $plan = $config['plans'][$id] ?? $default;
            foreach (['songs', 'videos', 'bytes'] as $key) {
                if (!isset($plan[$key]) || !is_int($plan[$key]) || $plan[$key] < 0) {
                    throw new RuntimeException('Plan limits must be nonnegative integers.');
                }
            }
            $this->plans[$id] = array_intersect_key($plan, $default);
        }
        $this->config = $config;
        $this->storage = $storage;
        if (is_link($storage . '/portal.sqlite')) {
            throw new RuntimeException('A symlinked database is not allowed.');
        }
        $this->database = new PDO('sqlite:' . $storage . '/portal.sqlite', null, null, [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        ]);
        $this->database->exec('PRAGMA foreign_keys = ON; PRAGMA busy_timeout = 5000; PRAGMA journal_mode = WAL;');
        $this->database->exec(<<<'SQL'
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                requested_plan TEXT NOT NULL DEFAULT 'free',
                effective_plan TEXT NOT NULL DEFAULT 'free',
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS media (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('audio','video')),
                mime TEXT NOT NULL,
                bytes INTEGER NOT NULL CHECK(bytes > 0),
                filename TEXT NOT NULL UNIQUE,
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS media_owner ON media(user_id, created_at);
            CREATE TABLE IF NOT EXISTS auth_attempts (
                bucket TEXT NOT NULL,
                attempted_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS auth_bucket ON auth_attempts(bucket, attempted_at);
            SQL);
        chmod($storage . '/portal.sqlite', 0600);
        ini_set('session.use_strict_mode', '1');
        ini_set('session.use_only_cookies', '1');
        ini_set('session.gc_maxlifetime', (string)$this->positiveOption('session_lifetime_seconds', 43200));
        session_name('mirroried_customer');
        session_save_path($storage . '/sessions');
        $script = (string)($_SERVER['SCRIPT_NAME'] ?? '/customer-portal/backend/api.php');
        $cookiePath = rtrim(str_replace('\\', '/', dirname(dirname($script))), '/') . '/';
        if (!preg_match('~^/[A-Za-z0-9_./-]*$~D', $cookiePath) || str_contains($cookiePath, '..')) {
            throw new RuntimeException('An invalid portal cookie path was found.');
        }
        session_set_cookie_params([
            'lifetime' => 0,
            'path' => $cookiePath,
            'secure' => $https,
            'httponly' => true,
            'samesite' => 'Strict',
        ]);
        if (!session_start()) {
            throw new RuntimeException('Private sessions are unavailable.');
        }
        $now = time();
        if (isset($_SESSION['user_id'])
            && ($now - (int)($_SESSION['last_seen'] ?? 0) > $this->positiveOption('session_idle_seconds', 7200)
                || $now - (int)($_SESSION['signed_in_at'] ?? 0) > $this->positiveOption('session_lifetime_seconds', 43200))) {
            $_SESSION = [];
            session_regenerate_id(true);
        }
        $_SESSION['last_seen'] = $now;
        if (!isset($_SESSION['csrf'])) {
            $_SESSION['csrf'] = bin2hex(random_bytes(32));
        }
        $this->configured = true;
        $this->status = 'Accounts and private uploads are enabled. Subscription plans are drafts; payments are off.';
    }

    private function isWithin(string $path, string $root): bool
    {
        return $path === $root || str_starts_with($path, rtrim($root, DIRECTORY_SEPARATOR) . DIRECTORY_SEPARATOR);
    }

    private function positiveOption(string $key, int $default): int
    {
        $value = $this->config[$key] ?? $default;
        if (!is_int($value) || $value < 1) {
            throw new RuntimeException('A positive server limit is required.');
        }
        return $value;
    }

    private function publicPlans(): array
    {
        $plans = [];
        foreach ($this->plans as $id => $limits) {
            $plans[] = ['id' => $id, 'name' => self::PLAN_NAMES[$id], 'songs' => $limits['songs'],
                'videos' => $limits['videos'], 'price' => null, 'draft' => true];
        }
        return $plans;
    }

    private function sessionData(): array
    {
        $user = $this->configured ? $this->currentUser() : null;
        return ['ok' => true, 'configured' => $this->configured, 'authenticated' => $user !== null,
            'user' => $user !== null ? $this->publicUser($user) : null,
            'csrf' => $this->configured ? (string)$_SESSION['csrf'] : null,
            'plans' => $this->publicPlans(), 'status' => $this->status,
            'capabilities' => ['signup' => $this->configured, 'upload' => $this->configured,
                'business' => $this->configured && ($this->config['business_enabled'] ?? false) === true,
                'hardwareSync' => false, 'payments' => false,
                'builderAi' => $this->configured && InfinityBuilder::aiAvailable($this->config, $user),
                'maxFileBytes' => ['audio' => $this->configured ? $this->positiveOption('max_audio_bytes', 67108864) : 67108864,
                    'video' => $this->configured ? $this->positiveOption('max_video_bytes', 134217728) : 134217728]]];
    }

    private function currentUser(): ?array
    {
        if (!isset($_SESSION['user_id']) || $this->database === null) {
            return null;
        }
        $query = $this->database->prepare('SELECT id,name,email,requested_plan,effective_plan FROM users WHERE id = ?');
        $query->execute([(int)$_SESSION['user_id']]);
        $user = $query->fetch();
        if ($user === false) {
            unset($_SESSION['user_id'], $_SESSION['signed_in_at']);
            return null;
        }
        return $user;
    }

    private function requireUser(): array
    {
        $user = $this->currentUser();
        if ($user === null) {
            throw new PortalError('Sign in to access your private media library.', 401);
        }
        return $user;
    }

    private function publicUser(array $user): array
    {
        return ['id' => (int)$user['id'], 'name' => $user['name'], 'email' => $user['email'],
            'roles' => BusinessPortal::roles($this->config, $user),
            'requestedPlan' => $user['requested_plan'],
            'effectivePlan' => array_key_exists($user['effective_plan'], $this->plans) ? $user['effective_plan'] : 'free'];
    }

    private function readJson(int $limit = 16384): array
    {
        if (!str_starts_with(strtolower((string)($_SERVER['CONTENT_TYPE'] ?? '')), 'application/json')) {
            throw new PortalError('Send this request as JSON.', 415);
        }
        $body = file_get_contents('php://input', false, null, 0, $limit + 1);
        if ($body === false || strlen($body) > $limit) {
            throw new PortalError('This request is too large.', 413);
        }
        try {
            $data = json_decode($body, true, 16, JSON_THROW_ON_ERROR);
        } catch (JsonException $error) {
            throw new PortalError('Send a valid JSON object.', 400);
        }
        if (!is_array($data) || array_is_list($data)) {
            throw new PortalError('Send a valid JSON object.', 400);
        }
        return $data;
    }

    private function requireCsrf(array $data): void
    {
        $origin = (string)($_SERVER['HTTP_ORIGIN'] ?? '');
        if ($origin !== '' && !hash_equals((string)$this->config['origin'], $origin)) {
            throw new PortalError('This request must come from the customer portal.', 403);
        }
        $csrf = $data['csrf'] ?? '';
        if (!is_string($csrf) || $csrf === '' || !hash_equals((string)($_SESSION['csrf'] ?? ''), $csrf)) {
            throw new PortalError('Your request token expired. Refresh the portal and try again.', 419);
        }
    }

    private function email(mixed $value): string
    {
        if (!is_string($value)) {
            throw new PortalError('Enter a valid email address.', 422);
        }
        $email = strtolower(trim($value));
        if (strlen($email) > 254 || !filter_var($email, FILTER_VALIDATE_EMAIL)) {
            throw new PortalError('Enter a valid email address.', 422);
        }
        return $email;
    }

    private function rateLimit(string $action, string $email): void
    {
        $limits = $this->config['auth_limits'] ?? [];
        $window = (int)($limits['window_seconds'] ?? 900);
        if ($window < 1) {
            throw new RuntimeException('Invalid authentication rate limit.');
        }
        $ip = (string)($_SERVER['REMOTE_ADDR'] ?? 'unknown');
        $buckets = $action === 'signup'
            ? ['signup-ip|' . $ip => (int)($limits['signup_ip'] ?? 10)]
            : ['login-ip|' . $ip => (int)($limits['login_ip'] ?? 50),
                'login-email|' . $email => (int)($limits['login_email'] ?? 10)];
        $now = time();
        $this->database->exec('BEGIN IMMEDIATE');
        try {
            $prune = $this->database->prepare('DELETE FROM auth_attempts WHERE attempted_at < ?');
            $prune->execute([$now - $window]);
            $count = $this->database->prepare('SELECT COUNT(*) FROM auth_attempts WHERE bucket = ? AND attempted_at >= ?');
            $add = $this->database->prepare('INSERT INTO auth_attempts(bucket,attempted_at) VALUES(?,?)');
            foreach ($buckets as $bucket => $maximum) {
                if ($maximum < 1) {
                    throw new RuntimeException('Invalid authentication rate limit.');
                }
                $hash = hash('sha256', $bucket);
                $count->execute([$hash, $now - $window]);
                if ((int)$count->fetchColumn() >= $maximum) {
                    header('Retry-After: ' . $window);
                    throw new PortalError('Too many sign-in attempts. Please wait before trying again.', 429);
                }
                $add->execute([$hash, $now]);
            }
            $this->database->exec('COMMIT');
        } catch (Throwable $error) {
            $this->database->exec('ROLLBACK');
            throw $error;
        }
    }

    private function authenticate(int $id): void
    {
        session_regenerate_id(true);
        $_SESSION = ['user_id' => $id, 'signed_in_at' => time(), 'last_seen' => time(),
            'csrf' => bin2hex(random_bytes(32))];
    }

    private function signup(array $data): never
    {
        $email = $this->email($data['email'] ?? null);
        $name = is_string($data['name'] ?? null) ? trim($data['name']) : '';
        $password = $data['password'] ?? null;
        $requestedPlan = $data['requestedPlan'] ?? 'free';
        if ($name === '' || strlen($name) > 120 || preg_match('/[\x00-\x1F\x7F]/', $name)) {
            throw new PortalError('Enter your name, up to 120 characters.', 422);
        }
        if (!is_string($password) || strlen($password) < 12 || strlen($password) > 72 || str_contains($password, "\0")) {
            throw new PortalError('Use a password between 12 and 72 bytes.', 422);
        }
        if (!is_string($requestedPlan) || !array_key_exists($requestedPlan, $this->plans)) {
            throw new PortalError('Choose one of the draft plans.', 422);
        }
        $this->rateLimit('signup', $email);
        $hash = password_hash($password, PASSWORD_DEFAULT);
        $this->database->exec('BEGIN IMMEDIATE');
        try {
            $query = $this->database->prepare('SELECT id FROM users WHERE email = ?');
            $query->execute([$email]);
            if ($query->fetchColumn() !== false) {
                throw new PortalError('An account already uses this email. Sign in instead.', 409);
            }
            $insert = $this->database->prepare('INSERT INTO users(name,email,password_hash,requested_plan,effective_plan,created_at) VALUES(?,?,?,?,?,?)');
            $insert->execute([$name, $email, $hash, $requestedPlan, 'free', time()]);
            $id = (int)$this->database->lastInsertId();
            $this->database->exec('COMMIT');
        } catch (Throwable $error) {
            $this->database->exec('ROLLBACK');
            throw $error;
        }
        $this->authenticate($id);
        portal_json($this->sessionData() + ['created' => true], 201);
    }

    private function login(array $data): never
    {
        $email = $this->email($data['email'] ?? null);
        $password = $data['password'] ?? null;
        if (!is_string($password) || strlen($password) > 72 || str_contains($password, "\0")) {
            throw new PortalError('Enter your email and password.', 422);
        }
        $this->rateLimit('login', $email);
        $query = $this->database->prepare('SELECT id,password_hash FROM users WHERE email = ?');
        $query->execute([$email]);
        $user = $query->fetch();
        // The fixed dummy hash preserves password-verification work for unknown accounts.
        $hash = $user !== false ? $user['password_hash'] : '$2y$10$92IXUNpkjO0rOQ5byMi.Ye4oKoEa3Ro9llC/.og/at2uheWG/igi.';
        $valid = password_verify($password, $hash);
        if ($user === false || !$valid) {
            throw new PortalError('The email or password was not accepted.', 401);
        }
        if (password_needs_rehash($user['password_hash'], PASSWORD_DEFAULT)) {
            $update = $this->database->prepare('UPDATE users SET password_hash = ? WHERE id = ?');
            $update->execute([password_hash($password, PASSWORD_DEFAULT), $user['id']]);
        }
        $clear = $this->database->prepare('DELETE FROM auth_attempts WHERE bucket = ?');
        $clear->execute([hash('sha256', 'login-email|' . $email)]);
        $this->authenticate((int)$user['id']);
        portal_json($this->sessionData());
    }

    private function logout(): never
    {
        $_SESSION = [];
        session_regenerate_id(true);
        $_SESSION['csrf'] = bin2hex(random_bytes(32));
        $_SESSION['last_seen'] = time();
        portal_json($this->sessionData());
    }

    private function usage(int $userId): array
    {
        $query = $this->database->prepare("SELECT COALESCE(SUM(kind = 'audio'),0) AS songs,COALESCE(SUM(kind = 'video'),0) AS videos,COALESCE(SUM(bytes),0) AS bytes FROM media WHERE user_id = ?");
        $query->execute([$userId]);
        return array_map('intval', $query->fetch());
    }

    private function limits(array $user): array
    {
        return $this->plans[$user['effective_plan']] ?? $this->plans['free'];
    }

    private function publicMedia(array $row): array
    {
        return ['id' => $row['id'], 'name' => $row['name'], 'kind' => $row['kind'], 'mime' => $row['mime'],
            'bytes' => (int)$row['bytes'], 'url' => 'backend/api.php?action=media&id=' . rawurlencode($row['id'])];
    }

    private function library(): never
    {
        $user = $this->requireUser();
        $query = $this->database->prepare('SELECT id,name,kind,mime,bytes FROM media WHERE user_id = ? ORDER BY created_at DESC,id DESC');
        $query->execute([$user['id']]);
        portal_json(['ok' => true, 'items' => array_map($this->publicMedia(...), $query->fetchAll()),
            'usage' => $this->usage((int)$user['id']), 'limits' => $this->limits($user)]);
    }

    private function inspectUpload(array $file): array
    {
        if (!isset($file['error']) || is_array($file['error']) || (int)$file['error'] !== UPLOAD_ERR_OK) {
            $error = isset($file['error']) && !is_array($file['error']) ? (int)$file['error'] : UPLOAD_ERR_NO_FILE;
            $large = in_array($error, [UPLOAD_ERR_INI_SIZE, UPLOAD_ERR_FORM_SIZE], true);
            throw new PortalError($large ? 'This file is larger than the server upload limit.' : 'Choose a complete audio or video file to upload.', $large ? 413 : 422);
        }
        $temporary = (string)($file['tmp_name'] ?? '');
        if (!is_uploaded_file($temporary)) {
            throw new PortalError('The uploaded file could not be verified.', 422);
        }
        $name = basename(str_replace('\\', '/', (string)($file['name'] ?? '')));
        if ($name === '' || strlen($name) > 200 || preg_match('/[\x00-\x1F\x7F]/', $name)
            || preg_match('/\.(?:php[0-9]?|phtml|phar|html?|js|svg|exe|bat|cmd|sh)(?:\.|$)/i', $name)) {
            throw new PortalError('Use a plain audio or video filename.', 422);
        }
        $extension = strtolower(pathinfo($name, PATHINFO_EXTENSION));
        $formats = [
            'mp3' => ['audio', ['audio/mpeg']],
            'wav' => ['audio', ['audio/x-wav', 'audio/wav', 'audio/vnd.wave']],
            'ogg' => ['audio', ['audio/ogg', 'application/ogg']],
            'mp4' => ['video', ['video/mp4']],
            'webm' => ['video', ['video/webm']],
        ];
        if (!isset($formats[$extension])) {
            throw new PortalError('Upload MP3, WAV or OGG audio, or MP4 or WebM video.', 422);
        }
        [$kind, $allowedMimes] = $formats[$extension];
        $bytes = filesize($temporary);
        if ($bytes === false || $bytes < 1 || $bytes !== (int)($file['size'] ?? -1)) {
            throw new PortalError('The uploaded file is empty or incomplete.', 422);
        }
        if ($bytes > $this->positiveOption($kind === 'audio' ? 'max_audio_bytes' : 'max_video_bytes', $kind === 'audio' ? 67108864 : 134217728)) {
            throw new PortalError('This file is larger than the allowed ' . $kind . ' file size.', 413);
        }
        $mime = (new finfo(FILEINFO_MIME_TYPE))->file($temporary);
        if (!is_string($mime) || !in_array($mime, $allowedMimes, true)) {
            throw new PortalError('The file contents do not match its audio or video extension.', 422);
        }
        $header = file_get_contents($temporary, false, null, 0, 65536);
        if ($header === false
            || ($extension === 'wav' && !(substr($header, 0, 4) === 'RIFF' && substr($header, 8, 4) === 'WAVE'))
            || ($extension === 'ogg' && !(str_starts_with($header, 'OggS')
                && (str_contains($header, 'OpusHead') || str_contains($header, "\x01vorbis")) && !str_contains($header, "\x80theora")))
            || ($extension === 'mp4' && substr($header, 4, 4) !== 'ftyp')
            || ($extension === 'webm' && !str_starts_with($header, "\x1a\x45\xdf\xa3"))) {
            throw new PortalError('The media container could not be verified.', 422);
        }
        return ['name' => $name, 'kind' => $kind, 'mime' => $extension === 'ogg' ? 'audio/ogg' : $mime,
            'bytes' => $bytes, 'temporary' => $temporary];
    }

    private function upload(): never
    {
        $user = $this->requireUser();
        if (!str_starts_with(strtolower((string)($_SERVER['CONTENT_TYPE'] ?? '')), 'multipart/form-data')) {
            throw new PortalError('Upload media using the file upload form.', 415);
        }
        if (!isset($_FILES['file']) || !is_array($_FILES['file'])) {
            throw new PortalError('Choose a file within the server upload limit.', 413);
        }
        $file = $this->inspectUpload($_FILES['file']);
        $id = bin2hex(random_bytes(16));
        $filename = $id . '.media';
        $destination = $this->storage . '/media/' . $filename;
        $moved = false;
        $this->database->exec('BEGIN IMMEDIATE');
        try {
            $limits = $this->limits($user);
            $usage = $this->usage((int)$user['id']);
            $counter = $file['kind'] === 'audio' ? 'songs' : 'videos';
            if ($usage[$counter] >= $limits[$counter]) {
                throw new PortalError('Your active plan has reached its ' . ($counter === 'songs' ? 'song' : 'video') . ' limit. Delete a file before uploading another.', 409);
            }
            if ($usage['bytes'] + $file['bytes'] > $limits['bytes']) {
                throw new PortalError('Your active plan has reached its private storage limit.', 409);
            }
            if (file_exists($destination) || !move_uploaded_file($file['temporary'], $destination)) {
                throw new RuntimeException('Private upload could not be stored.');
            }
            $moved = true;
            chmod($destination, 0600);
            $insert = $this->database->prepare('INSERT INTO media(id,user_id,name,kind,mime,bytes,filename,created_at) VALUES(?,?,?,?,?,?,?,?)');
            $insert->execute([$id, $user['id'], $file['name'], $file['kind'], $file['mime'], $file['bytes'], $filename, time()]);
            $this->database->exec('COMMIT');
        } catch (Throwable $error) {
            $this->database->exec('ROLLBACK');
            if ($moved && is_file($destination)) {
                unlink($destination);
            }
            throw $error;
        }
        portal_json(['ok' => true, 'item' => $this->publicMedia($file + ['id' => $id]),
            'usage' => $this->usage((int)$user['id']), 'limits' => $this->limits($user)], 201);
    }

    private function ownedMedia(array $user, mixed $id): array
    {
        if (!is_string($id) || !preg_match('/^[a-f0-9]{32}$/D', $id)) {
            throw new PortalError('This media item is unavailable.', 404);
        }
        $query = $this->database->prepare('SELECT id,name,kind,mime,bytes,filename FROM media WHERE id = ? AND user_id = ?');
        $query->execute([$id, $user['id']]);
        $row = $query->fetch();
        if ($row === false || !preg_match('/^[a-f0-9]{32}\.media$/D', $row['filename'])) {
            throw new PortalError('This media item is unavailable.', 404);
        }
        return $row;
    }

    private function mediaPath(array $row): string
    {
        $path = $this->storage . '/media/' . $row['filename'];
        if (!is_file($path) || is_link($path) || realpath($path) !== $path) {
            throw new PortalError('This media item is unavailable.', 404);
        }
        return $path;
    }

    private function delete(array $data): never
    {
        $user = $this->requireUser();
        $this->database->exec('BEGIN IMMEDIATE');
        try {
            $row = $this->ownedMedia($user, $data['id'] ?? null);
            $path = $this->mediaPath($row);
            if (!unlink($path)) {
                throw new RuntimeException('Private file could not be removed.');
            }
            $query = $this->database->prepare('DELETE FROM media WHERE id = ? AND user_id = ?');
            $query->execute([$row['id'], $user['id']]);
            $this->database->exec('COMMIT');
        } catch (Throwable $error) {
            $this->database->exec('ROLLBACK');
            throw $error;
        }
        portal_json(['ok' => true, 'usage' => $this->usage((int)$user['id']), 'limits' => $this->limits($user)]);
    }

    private function media(): never
    {
        $user = $this->requireUser();
        $row = $this->ownedMedia($user, $_GET['id'] ?? null);
        $path = $this->mediaPath($row);
        $size = filesize($path);
        if ($size === false || $size < 1 || $size !== (int)$row['bytes']) {
            throw new PortalError('This media item is unavailable.', 404);
        }
        $start = 0;
        $end = $size - 1;
        $range = (string)($_SERVER['HTTP_RANGE'] ?? '');
        if ($range !== '') {
            if (!preg_match('/^bytes=([0-9]*)-([0-9]*)$/D', $range, $matches)
                || ($matches[1] === '' && $matches[2] === '')) {
                header('Content-Range: bytes */' . $size);
                throw new PortalError('This media range is unavailable.', 416);
            }
            if ($matches[1] === '') {
                $suffix = (int)$matches[2];
                if ($suffix < 1) {
                    header('Content-Range: bytes */' . $size);
                    throw new PortalError('This media range is unavailable.', 416);
                }
                $start = max(0, $size - $suffix);
            } else {
                $start = (int)$matches[1];
                $end = $matches[2] === '' ? $end : min($end, (int)$matches[2]);
            }
            if ($start >= $size || $end < $start) {
                header('Content-Range: bytes */' . $size);
                throw new PortalError('This media range is unavailable.', 416);
            }
            http_response_code(206);
            header('Content-Range: bytes ' . $start . '-' . $end . '/' . $size);
        }
        $stream = fopen($path, 'rb');
        if ($stream === false || fseek($stream, $start) !== 0) {
            throw new RuntimeException('Private media could not be read.');
        }
        // Release the session lock while a player streams; other portal actions can continue.
        session_write_close();
        header('Content-Type: ' . $row['mime']);
        header('Content-Length: ' . ($end - $start + 1));
        header('Accept-Ranges: bytes');
        header("Content-Disposition: inline; filename=\"media\"; filename*=UTF-8''" . rawurlencode($row['name']));
        $remaining = $end - $start + 1;
        while ($remaining > 0 && !feof($stream) && !connection_aborted()) {
            $chunk = fread($stream, min(65536, $remaining));
            if ($chunk === false || $chunk === '') {
                break;
            }
            echo $chunk;
            $remaining -= strlen($chunk);
        }
        fclose($stream);
        exit;
    }
}
