<?php
declare(strict_types=1);

/* Private implementation. Install outside public_html; expose only mcp.php. */

final class WorkflowError extends RuntimeException
{
    public function __construct(public readonly string $kind, string $message)
    {
        parent::__construct($message);
    }
}

function wf_require(bool $condition, string $message, string $kind = 'invalid_arguments'): void
{
    if (!$condition) {
        throw new WorkflowError($kind, $message);
    }
}

function wf_json(mixed $value): string
{
    return json_encode($value, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR) . "\n";
}

function wf_now(): string { return gmdate('Y-m-d\TH:i:s\Z'); }

function wf_cell(mixed $value): string
{
    return str_replace(["|", "\n"], ["\\|", ' '], (string)$value);
}

/* Keep this renderer byte-identical to tools/ai_workflow.py; parity is tested. */
function wf_render(array $state, array $queue): string
{
    $repo = $state['repository']; $source = $state['source']; $deploy = $state['deployment'];
    $attempt = $deploy['last_attempt'];
    $connections = $state['connector']['summary'] ?? 'Instructions and local logger available; common remote connector is queued';
    $lines = ['# Mirroried LED shared work status', '',
        'Evidence snapshot: ' . $state['observed_at'] . ' (UTC). Refresh GitHub at the start of each session.', '',
        '| Area | Recorded state |', '| --- | --- |',
        '| Repository | [' . $repo['full_name'] . '](' . $repo['url'] . ') · ' . $repo['default_branch'] . ' |',
        '| Observed website source | [' . substr($source['observed_commit'], 0, 7) . '](' . $source['evidence_url'] . ') · ' . wf_cell($source['summary']) . ' |',
        '| Verified live Hostinger commit | ' . ($deploy['live_commit'] ?? 'Unknown — no verified live commit recorded') . ' |',
        '| Last Hostinger attempt | [' . wf_cell($attempt['status']) . '](' . $attempt['evidence_url'] . ') · ' . wf_cell($attempt['failed_step']) . ' |',
        '| Deployment blocker | ' . wf_cell($attempt['finding']) . ' |',
        '| Shared app connections | ' . wf_cell($connections) . ' |', '', '## Source checks', ''];
    foreach ($source['checks'] as $check) {
        $lines[] = '- [' . wf_cell($check['name']) . '](' . $check['evidence_url'] . '): **' . $check['result'] . '**.';
    }
    array_push($lines, '', '## Task queue', '', '| Task | Status | Owner session | Next action |', '| --- | --- | --- | --- |');
    $tasks = $queue['tasks'];
    usort($tasks, fn($a, $b) => [$a['priority'], $a['id']] <=> [$b['priority'], $b['id']]);
    foreach ($tasks as $task) {
        $lines[] = '| ' . $task['id'] . ' — ' . wf_cell($task['title']) . ' | ' . $task['status'] . ' | ' . ($task['owner_session_id'] ?? 'Unclaimed') . ' | ' . wf_cell($task['next_action']) . ' |';
    }
    array_push($lines, '', '## Continue', '',
        'First operational task: **' . $state['next_task_id'] . '**. Independent ready tasks may proceed after checking ownership.', '',
        'Read [the workflow guide](README.md), the actual GitHub HEAD and open PRs, and the relevant feature/release docs.',
        'See [session records](sessions/) and [imported GitHub evidence](history/github-baseline.json).', '',
        'This record does not grant account access or capture all chats automatically. Older AI identities remain unknown.',
        "A green source check or GitHub Pages deployment does not establish the live PHP website's version.", '');
    return implode("\n", $lines);
}

final class WorkflowGitHub
{
    private ?Closure $transport;
    private array $config;
    private ?string $account = null;
    public const PREFIX = 'docs/ai-workflow/';

    public function __construct(array $config, ?Closure $transport = null)
    {
        $this->config = $config;
        $this->transport = $transport;
    }

    public function request(string $method, string $path, ?array $body = null): array
    {
        if ($this->transport !== null) {
            return ($this->transport)($method, $path, $body);
        }
        wf_require(extension_loaded('curl'), 'PHP cURL is required.', 'configuration');
        $curl = curl_init('https://api.github.com' . $path);
        curl_setopt_array($curl, [CURLOPT_RETURNTRANSFER => true, CURLOPT_FOLLOWLOCATION => false,
            CURLOPT_CONNECTTIMEOUT => 5, CURLOPT_TIMEOUT => 20, CURLOPT_CUSTOMREQUEST => $method,
            CURLOPT_PROTOCOLS => CURLPROTO_HTTPS, CURLOPT_SSL_VERIFYPEER => true, CURLOPT_SSL_VERIFYHOST => 2,
            CURLOPT_HTTPHEADER => ['Accept: application/vnd.github+json', 'User-Agent: MirroriedLED-Workflow/1.0',
                'X-GitHub-Api-Version: 2022-11-28', 'Content-Type: application/json',
                'Authorization: Bearer ' . $this->config['github_token']]]);
        if ($body !== null) { curl_setopt($curl, CURLOPT_POSTFIELDS, wf_json($body)); }
        $raw = curl_exec($curl); $status = curl_getinfo($curl, CURLINFO_HTTP_CODE); curl_close($curl);
        wf_require(is_string($raw) && $status > 0, 'GitHub could not be reached; retry with the same request_id.', 'upstream_unavailable');
        // Never include upstream response bodies, credentials, or URLs with tokens in errors.
        if ($status === 409 || $status === 422) { throw new WorkflowError('ref_conflict', 'GitHub refused the branch update.'); }
        wf_require($status >= 200 && $status < 300, 'GitHub access failed (HTTP ' . $status . '); check token permissions, expiry, repository rules and rate limits.', 'github_access');
        try { $result = json_decode($raw, true, 64, JSON_THROW_ON_ERROR); }
        catch (JsonException) { throw new WorkflowError('upstream_unavailable', 'GitHub returned an invalid response.'); }
        wf_require(is_array($result), 'GitHub returned an invalid response.', 'upstream_unavailable');
        return $result;
    }

    public function repoPath(string $suffix): string
    {
        return '/repos/' . $this->config['repository'] . '/' . $suffix;
    }

    public function account(): string
    {
        if ($this->account === null) {
            $login = $this->request('GET', '/user')['login'] ?? null;
            wf_require($login === $this->config['expected_github_account'], 'The service GitHub account does not match its configuration.', 'github_identity');
            $this->account = $login;
        }
        return $this->account;
    }

    public function head(): string
    {
        $sha = $this->request('GET', $this->repoPath('git/ref/heads/' . rawurlencode($this->config['branch'])))['object']['sha'] ?? '';
        wf_require((bool)preg_match('/^[a-f0-9]{40}$/D', $sha), 'Invalid GitHub HEAD.', 'upstream_unavailable');
        return $sha;
    }

    public function read(string $path, string $head, bool $optional = false): ?array
    {
        $url = $this->repoPath('contents/' . $path) . '?ref=' . $head;
        // Optional files are discovered in the pinned tree; do not suppress authorization failures.
        if ($optional && !$this->exists($path, $head)) { return null; }
        $data = $this->request('GET', $url);
        wf_require(($data['encoding'] ?? '') === 'base64', 'Unsupported GitHub file encoding.', 'upstream_unavailable');
        $text = base64_decode($data['content'] ?? '', true);
        wf_require(is_string($text) && strlen($text) <= 1048576, 'Invalid or oversized workflow record.', 'invalid_record');
        try { $record = json_decode($text, true, 64, JSON_THROW_ON_ERROR); }
        catch (JsonException) { throw new WorkflowError('invalid_record', 'A shared record contains invalid JSON.'); }
        wf_require(is_array($record), 'A shared record must be an object.', 'invalid_record');
        return $record;
    }

    private array $treeCache = [];
    public function tree(string $head): array
    {
        if (!isset($this->treeCache[$head])) {
            $data = $this->request('GET', $this->repoPath('git/trees/' . $head) . '?recursive=1');
            wf_require(empty($data['truncated']), 'The repository tree is too large for this connector; no write was made.', 'invalid_record');
            $this->treeCache[$head] = $data['tree'];
        }
        return $this->treeCache[$head];
    }

    public function exists(string $path, string $head): bool
    {
        foreach ($this->tree($head) as $entry) {
            if ($entry['path'] === $path) {
                wf_require(($entry['mode'] ?? '') === '100644' && ($entry['type'] ?? '') === 'blob', 'Unsafe shared record type.', 'invalid_record');
                return true;
            }
        }
        return false;
    }

    public function snapshot(): array
    {
        $this->account();
        $head = $this->head();
        $state = $this->read(self::PREFIX . 'state.json', $head);
        $queue = $this->read(self::PREFIX . 'tasks.json', $head);
        wf_require(($state['schema_version'] ?? 0) === 1 && ($queue['schema_version'] ?? 0) === 1 && is_array($queue['tasks'] ?? null), 'Unsupported shared record format.', 'invalid_record');
        wf_require(($state['repository']['full_name'] ?? '') === $this->config['repository'], 'Shared state identifies a different repository.', 'invalid_record');
        $ids = [];
        foreach ($queue['tasks'] as $task) {
            wf_require(is_array($task) && preg_match('/^WF-[0-9]{3,}$/D', $task['id'] ?? '') === 1 && !isset($ids[$task['id']]), 'Invalid or duplicate task.', 'invalid_record');
            $ids[$task['id']] = true;
            wf_require(in_array($task['status'] ?? '', ['ready', 'in_progress', 'blocked', 'done'], true) && is_array($task['depends_on'] ?? null), 'Invalid task format.', 'invalid_record');
            wf_require(($task['status'] === 'in_progress') === is_string($task['owner_session_id'] ?? null), 'Task ownership is inconsistent.', 'invalid_record');
        }
        foreach ($queue['tasks'] as $task) {
            foreach ($task['depends_on'] as $dependency) { wf_require(isset($ids[$dependency]), 'Unknown task dependency.', 'invalid_record'); }
        }
        return ['head' => $head, 'state' => $state, 'queue' => $queue];
    }

    public function publish(string $head, array $files, string $message): string
    {
        $entries = [];
        foreach ($files as $path => $text) {
            wf_require($path === self::PREFIX . 'tasks.json' || $path === self::PREFIX . 'CURRENT_STATUS.md'
                || preg_match('~^docs/ai-workflow/sessions/[a-z0-9][a-z0-9_-]{0,95}\.json$~D', $path) === 1,
                'The connector can write only task, status and session records.');
            $entries[] = ['path' => $path, 'mode' => '100644', 'type' => 'blob', 'content' => $text];
        }
        $base = $this->request('GET', $this->repoPath('git/commits/' . $head));
        $tree = $this->request('POST', $this->repoPath('git/trees'), ['base_tree' => $base['tree']['sha'], 'tree' => $entries]);
        $commit = $this->request('POST', $this->repoPath('git/commits'), ['message' => $message, 'tree' => $tree['sha'], 'parents' => [$head]]);
        // Sibling commits from concurrent clients cannot both fast-forward this ref.
        $this->request('PATCH', $this->repoPath('git/refs/heads/' . rawurlencode($this->config['branch'])), ['sha' => $commit['sha'], 'force' => false]);
        return $commit['sha'];
    }
}

final class MirroriedWorkflowServer
{
    public const VERSIONS = ['2025-06-18', '2025-03-26'];
    public const INSTRUCTIONS = 'Read read_state and read_history before website work. Start a session with a unique request_id and task_id before editing. A task claim is global only after GitHub publication succeeds. Use claim_task for another task and finish_session with actual changes, checks, evidence and the next action. These tools update work records only; use the app\'s GitHub tools for website code and PRs. Source checks do not prove Hostinger deployment. Keep credentials and private customer/chat data out of summaries.';
    private WorkflowGitHub $github;

    public function __construct(private array $config, ?WorkflowGitHub $github = null)
    {
        self::validateConfig($config);
        $this->github = $github ?? new WorkflowGitHub($config);
    }

    public static function validateConfig(array $config): void
    {
        wf_require(($config['repository'] ?? '') === 'Crosby121/MirroriedLED-Public' && ($config['branch'] ?? '') === 'main', 'This connector is scoped to Mirroried LED work records on main.', 'configuration');
        wf_require(($config['expected_github_account'] ?? '') === 'Crosby121' && is_string($config['github_token'] ?? null)
            && strlen($config['github_token']) >= 30 && !preg_match('/[\r\n]/', $config['github_token']), 'Configure the expected service GitHub account and its token.', 'configuration');
        wf_require(is_array($config['clients'] ?? null) && count($config['clients']) >= 1 && count($config['clients']) <= 20, 'Configure at least one app credential.', 'configuration');
        $hashes = [];
        foreach ($config['clients'] as $id => $client) {
            wf_require(is_string($id) && preg_match('/^[a-z0-9][a-z0-9_-]{0,31}$/D', $id) === 1
                && is_array($client) && is_string($client['application'] ?? null) && strlen($client['application']) >= 1
                && strlen($client['application']) <= 120 && !preg_match('/[\x00-\x1f]/', $client['application'])
                && preg_match('/^[a-f0-9]{64}$/D', $client['token_sha256'] ?? '') === 1, 'Invalid app credential configuration.', 'configuration');
            wf_require(!isset($hashes[$client['token_sha256']]), 'Use a different credential for every app.', 'configuration');
            $hashes[$client['token_sha256']] = true;
        }
        wf_require(is_array($config['allowed_origins'] ?? null), 'Configure allowed browser origins.', 'configuration');
        foreach ($config['allowed_origins'] as $origin) {
            wf_require(is_string($origin) && preg_match('~^https://[a-z0-9.-]+(?::[0-9]+)?$~D', $origin) === 1, 'Allowed origins must be explicit HTTPS origins.', 'configuration');
        }
    }

    private function authenticate(array $headers): array
    {
        $origin = $headers['origin'] ?? null;
        wf_require($origin === null || in_array($origin, $this->config['allowed_origins'], true), 'Browser origin is not allowed.', 'forbidden_origin');
        $authorization = $headers['authorization'] ?? '';
        wf_require(preg_match('/^Bearer (mlwf_[a-zA-Z0-9_-]{40,128})$/D', $authorization, $matches) === 1, 'An app credential is required.', 'unauthorized');
        $hash = hash('sha256', $matches[1]);
        foreach ($this->config['clients'] as $id => $client) {
            if (hash_equals($client['token_sha256'], $hash)) { return ['id' => $id, 'application' => $client['application'], 'token' => $matches[1]]; }
        }
        throw new WorkflowError('unauthorized', 'The app credential is not valid.');
    }

    public function handle(string $method, array $headers, string $body): array
    {
        $headers = array_change_key_case($headers, CASE_LOWER);
        try { $client = $this->authenticate($headers); }
        catch (WorkflowError $e) { return $this->httpError($e->kind === 'unauthorized' ? 401 : 403, $e->getMessage()); }
        if ($method !== 'POST') { return $this->httpError(405, 'Use POST for MCP requests.'); }
        $version = $headers['mcp-protocol-version'] ?? '2025-03-26';
        if (!in_array($version, self::VERSIONS, true)) { return $this->httpError(400, 'Unsupported MCP protocol version.'); }
        if (strlen($body) > 131072) { return $this->httpError(413, 'Request is too large.'); }
        if (strtolower(trim(explode(';', $headers['content-type'] ?? '')[0])) !== 'application/json') {
            return $this->httpError(415, 'Use application/json.');
        }
        $accept = strtolower($headers['accept'] ?? '');
        if (!str_contains($accept, 'application/json') || !str_contains($accept, 'text/event-stream')) {
            return $this->httpError(406, 'Accept application/json and text/event-stream.');
        }
        try { $message = json_decode($body, true, 64, JSON_THROW_ON_ERROR); }
        catch (JsonException) { return [400, $this->rpcError(null, -32700, 'Invalid JSON.')]; }
        if (!is_array($message) || array_is_list($message) || ($message['jsonrpc'] ?? '') !== '2.0' || !is_string($message['method'] ?? null)) {
            return [400, $this->rpcError(null, -32600, 'Invalid JSON-RPC request.')];
        }
        if (!array_key_exists('id', $message)) {
            if (str_starts_with($message['method'], 'notifications/')) { return [202, null]; }
            return [400, $this->rpcError(null, -32600, 'A request ID is required.')];
        }
        $id = $message['id'];
        if (!is_string($id) && !is_int($id)) { return [400, $this->rpcError(null, -32600, 'Invalid request ID.')]; }
        $params = $message['params'] ?? [];
        if (!is_array($params)) { return [200, $this->rpcError($id, -32602, 'Parameters must be an object.')]; }
        try {
            if ($message['method'] === 'initialize') {
                $requested = $params['protocolVersion'] ?? '';
                $result = ['protocolVersion' => in_array($requested, self::VERSIONS, true) ? $requested : self::VERSIONS[0],
                    'capabilities' => ['tools' => ['listChanged' => false]], 'serverInfo' => ['name' => 'mirroriedLedWorkflow', 'version' => '1.0.0'],
                    'instructions' => self::INSTRUCTIONS];
            } elseif ($message['method'] === 'ping') { $result = new stdClass(); }
            elseif ($message['method'] === 'tools/list') { $result = ['tools' => $this->tools()]; }
            elseif ($message['method'] === 'tools/call') {
                wf_require(is_string($params['name'] ?? null) && is_array($params['arguments'] ?? []), 'Specify a tool name and argument object.');
                try { $data = $this->call($params['name'], $params['arguments'] ?? [], $client); $result = $this->toolResult($data); }
                catch (WorkflowError $e) { $result = $this->toolResult(['error' => ['code' => $e->kind, 'message' => $e->getMessage(),
                    'retryable' => in_array($e->kind, ['ref_conflict', 'upstream_unavailable'], true)]], true); }
            } else { return [200, $this->rpcError($id, -32601, 'Method not found.')]; }
            return [200, ['jsonrpc' => '2.0', 'id' => $id, 'result' => $result]];
        } catch (WorkflowError $e) { return [200, $this->rpcError($id, -32602, $e->getMessage())]; }
    }

    private function httpError(int $status, string $message): array { return [$status, ['error' => $message]]; }
    private function rpcError(mixed $id, int $code, string $message): array { return ['jsonrpc' => '2.0', 'id' => $id, 'error' => ['code' => $code, 'message' => $message]]; }
    private function toolResult(array $data, bool $error = false): array { return ['content' => [['type' => 'text', 'text' => wf_json($data)]], 'structuredContent' => $data, 'isError' => $error]; }

    private function tools(): array
    {
        $str = ['type' => 'string', 'minLength' => 1];
        $task = ['type' => 'string', 'pattern' => '^WF-[0-9]{3,}$'];
        $sid = ['type' => 'string', 'pattern' => '^[a-z0-9][a-z0-9_-]{0,95}$'];
        $definitions = [
            ['read_state', 'Read the pinned GitHub work state, queue and current repository HEAD. Source/deployment observations retain their dates.', [], [], true],
            ['read_history', 'Read session handoffs and the sourced GitHub baseline. Pagination uses an opaque session cursor.',
                ['limit' => ['type' => 'integer', 'minimum' => 1, 'maximum' => 30], 'cursor' => $sid], [], true],
            ['start_session', 'Atomically start and publish a work session with its first task. Reuse request_id after an uncertain response; do not edit until success.',
                ['request_id' => ['type' => 'string', 'pattern' => '^[A-Za-z0-9_-]{8,80}$'], 'application' => $str, 'task_id' => $task,
                    'branch' => $str, 'base_commit' => ['type' => 'string', 'pattern' => '^[a-f0-9]{40}$']], ['request_id', 'application', 'task_id', 'branch', 'base_commit'], false],
            ['claim_task', 'Reserve another ready or blocked task for your active session. An existing claim held by another session is a conflict.',
                ['session_id' => $sid, 'task_id' => $task], ['session_id', 'task_id'], false],
            ['finish_session', 'Publish actual changes, checks and handoff; close the session and release all its tasks. Completed means done; blocked permits a later takeover.',
                ['session_id' => $sid, 'outcome' => ['enum' => ['completed', 'blocked']], 'summary' => $str, 'next_action' => $str,
                    'changed_files' => ['type' => 'array', 'maxItems' => 100, 'items' => $str],
                    'checks' => ['type' => 'array', 'maxItems' => 30, 'items' => ['type' => 'object', 'additionalProperties' => false,
                        'properties' => ['name' => $str, 'result' => ['enum' => ['passed', 'failed', 'skipped', 'not_run']], 'command' => $str, 'evidence_url' => $str], 'required' => ['name', 'result']]],
                    'evidence_urls' => ['type' => 'array', 'maxItems' => 30, 'items' => $str]],
                ['session_id', 'outcome', 'summary', 'next_action', 'changed_files', 'checks'], false],
        ];
        return array_map(fn($d) => ['name' => $d[0], 'description' => $d[1],
            'inputSchema' => ['type' => 'object', 'properties' => $d[2] ?: new stdClass(), 'required' => $d[3], 'additionalProperties' => false],
            'annotations' => ['readOnlyHint' => $d[4], 'destructiveHint' => false, 'idempotentHint' => true, 'openWorldHint' => true]], $definitions);
    }

    private function checkArguments(string $name, array $args, array $client): void
    {
        $definition = null;
        foreach ($this->tools() as $tool) { if ($tool['name'] === $name) { $definition = $tool['inputSchema']; } }
        wf_require($definition !== null, 'Unknown workflow tool.');
        foreach ($definition['required'] as $key) { wf_require(array_key_exists($key, $args), 'Missing required field: ' . $key); }
        $properties = (array)$definition['properties'];
        foreach ($args as $key => $value) {
            wf_require(isset($properties[$key]), 'Unexpected tool argument.');
            $schema = $properties[$key];
            if (($schema['type'] ?? '') === 'string') { wf_require(is_string($value) && strlen($value) >= 1 && strlen($value) <= 8000 && !str_contains($value, "\0"), 'Invalid string argument.'); }
            if (isset($schema['pattern'])) { wf_require(is_string($value) && preg_match('~' . $schema['pattern'] . '~D', $value) === 1, 'Invalid argument format.'); }
            if (isset($schema['enum'])) { wf_require(in_array($value, $schema['enum'], true), 'Invalid argument value.'); }
            if (($schema['type'] ?? '') === 'array') { wf_require(is_array($value) && array_is_list($value) && count($value) <= $schema['maxItems'], 'Invalid array argument.'); }
            if (($schema['type'] ?? '') === 'integer') { wf_require(is_int($value) && $value >= $schema['minimum'] && $value <= $schema['maximum'], 'Invalid numeric argument.'); }
        }
        $text = wf_json($args);
        wf_require(!preg_match('/-----BEGIN [A-Z ]*PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{30,}|mlwf_[A-Za-z0-9_-]{40,}/', $text)
            && !str_contains($text, $client['token']) && !str_contains($text, $this->config['github_token']), 'Remove credentials from the work record before publishing.');
        if (isset($args['application'])) { wf_require($args['application'] === $client['application'], 'The declared app must match the label assigned to this app credential.'); }
        if (isset($args['branch'])) { wf_require(preg_match('~^[A-Za-z0-9][A-Za-z0-9._/-]{0,119}$~D', $args['branch']) === 1 && !str_contains($args['branch'], '..'), 'Invalid work branch.'); }
        foreach ($args['changed_files'] ?? [] as $path) {
            wf_require(is_string($path) && strlen($path) <= 240 && preg_match('~^[A-Za-z0-9._-][A-Za-z0-9._/ -]*$~D', $path) === 1
                && !in_array('..', explode('/', $path), true), 'Changed files must be safe repository-relative paths.');
        }
        foreach ($args['checks'] ?? [] as $check) {
            wf_require(is_array($check) && is_string($check['name'] ?? null) && strlen($check['name']) > 0 && strlen($check['name']) <= 500
                && in_array($check['result'] ?? '', ['passed', 'failed', 'skipped', 'not_run'], true)
                && !array_diff(array_keys($check), ['name', 'result', 'command', 'evidence_url']), 'Invalid check record.');
            foreach (['command', 'evidence_url'] as $field) { if (isset($check[$field])) { wf_require(is_string($check[$field]) && strlen($check[$field]) >= 1 && strlen($check[$field]) <= 2000, 'Invalid check detail.'); } }
            if (isset($check['evidence_url'])) { $this->checkUrl($check['evidence_url']); }
        }
        foreach ($args['evidence_urls'] ?? [] as $url) { $this->checkUrl($url); }
    }

    private function checkUrl(mixed $url): void
    {
        $fragment = is_string($url) ? parse_url($url, PHP_URL_FRAGMENT) : null;
        $safeFragment = $fragment === null || (parse_url($url, PHP_URL_HOST) === 'github.com'
            && preg_match('/^(?:discussion_r|issuecomment-|pullrequestreview-|commitcomment-)[0-9]+$/D', $fragment) === 1);
        wf_require(is_string($url) && strlen($url) <= 2000 && filter_var($url, FILTER_VALIDATE_URL) !== false
            && parse_url($url, PHP_URL_SCHEME) === 'https' && parse_url($url, PHP_URL_USER) === null && parse_url($url, PHP_URL_PASS) === null
            && parse_url($url, PHP_URL_QUERY) === null && $safeFragment,
            'Use HTTPS evidence without credentials or query parameters; only standard GitHub comment fragments are allowed.');
    }

    private function taskIndex(array $queue, string $taskId): int
    {
        foreach ($queue['tasks'] as $index => $task) { if ($task['id'] === $taskId) { return $index; } }
        throw new WorkflowError('unknown_task', 'The task does not exist.');
    }

    private function available(array $queue, int $index, string $sessionId): void
    {
        $task = $queue['tasks'][$index];
        wf_require($task['status'] !== 'done', 'The task is already complete.', 'task_conflict');
        wf_require($task['owner_session_id'] === null || $task['owner_session_id'] === $sessionId,
            'The task is owned by another session: ' . ($task['owner_session_id'] ?? ''), 'task_conflict');
        foreach ($task['depends_on'] as $dependency) {
            wf_require($queue['tasks'][$this->taskIndex($queue, $dependency)]['status'] === 'done', 'A prerequisite task is unfinished.', 'task_dependency');
        }
    }

    private function ownedSession(string $id, string $head, array $client): array
    {
        $session = $this->github->read(WorkflowGitHub::PREFIX . 'sessions/' . $id . '.json', $head, true);
        wf_require($session !== null, 'The session does not exist.', 'unknown_session');
        wf_require(($session['authenticated_client_id'] ?? null) === $client['id'], 'This app credential does not own that session.', 'session_owner');
        return $session;
    }

    private function receipt(array $snapshot, array $client, ?array $session = null, ?string $commit = null): array
    {
        $data = ['repository' => $this->config['repository'], 'record_branch' => 'main', 'github_head_read' => $snapshot['head'],
            'checked_at' => wf_now(), 'authenticated_client_id' => $client['id'], 'configured_application' => $client['application'],
            'application_identity_basis' => 'declared_app_and_configured_credential_label; not proof of a physical application',
            'service_github_account' => $this->github->account(), 'commit' => $commit,
            'evidence_url' => 'https://github.com/' . $this->config['repository'] . '/commit/' . ($commit ?? $snapshot['head'])];
        if ($session !== null) { $data['session'] = $session; }
        return $data;
    }

    private function call(string $name, array $args, array $client): array
    {
        $this->checkArguments($name, $args, $client);
        if ($name === 'read_state') {
            $snapshot = $this->github->snapshot();
            $recent = []; $seen = [];
            foreach ($snapshot['queue']['tasks'] as $task) {
                $id = $task['owner_session_id'] ?? $task['last_session_id'];
                if (is_string($id) && !isset($seen[$id]) && count($recent) < 20) {
                    wf_require(preg_match('/^[a-z0-9][a-z0-9_-]{0,95}$/D', $id) === 1, 'Invalid session reference.', 'invalid_record');
                    $seen[$id] = true;
                    $recent[] = $this->github->read(WorkflowGitHub::PREFIX . 'sessions/' . $id . '.json', $snapshot['head']);
                }
            }
            usort($recent, fn($a, $b) => ($b['ended_at'] ?? $b['started_at']) <=> ($a['ended_at'] ?? $a['started_at']));
            return $this->receipt($snapshot, $client) + ['state' => $snapshot['state'], 'tasks' => $snapshot['queue'],
                'recent_task_sessions' => $recent,
                'source_observation_matches_head' => $snapshot['state']['source']['observed_commit'] === $snapshot['head']];
        }
        if ($name === 'read_history') { return $this->history($args, $client); }
        // Retry only an actual moving-head conflict. Never force or bypass repository rules.
        for ($attempt = 0; $attempt < 4; $attempt++) {
            $snapshot = $this->github->snapshot(); $head = $snapshot['head']; $queue = $snapshot['queue'];
            $id = $args['session_id'] ?? ('mcp-' . $client['id'] . '-' . substr(hash('sha256', $args['request_id']), 0, 24));
            $sessionPath = WorkflowGitHub::PREFIX . 'sessions/' . $id . '.json';
            if ($name === 'start_session') {
                $existing = $this->github->read($sessionPath, $head, true);
                $fingerprint = hash('sha256', wf_json([$args['application'], $args['task_id'], $args['branch'], $args['base_commit']]));
                if ($existing !== null) {
                    wf_require(($existing['authenticated_client_id'] ?? '') === $client['id'] && ($existing['start_fingerprint'] ?? '') === $fingerprint,
                        'request_id was previously used for a different session request.', 'idempotency_conflict');
                    return $this->receipt($snapshot, $client, $existing) + ['replayed' => true];
                }
                $index = $this->taskIndex($queue, $args['task_id']); $this->available($queue, $index, $id);
                $session = ['schema_version' => 1, 'id' => $id, 'application' => $args['application'], 'application_identity' => 'declared',
                    'authenticated_client_id' => $client['id'], 'credential_label' => $client['application'],
                    'github_account' => $this->github->account(), 'github_account_basis' => 'authenticated_service_token; not the individual app user',
                    'started_at' => wf_now(), 'ended_at' => null, 'status' => 'active', 'task_ids' => [$args['task_id']],
                    'branch' => $args['branch'], 'base_commit' => $args['base_commit'], 'github_head_at_start' => $head,
                    'summary' => null, 'next_action' => null, 'changed_files' => [], 'checks' => [], 'findings' => [], 'start_fingerprint' => $fingerprint];
                $queue['tasks'][$index]['status'] = 'in_progress'; $queue['tasks'][$index]['owner_session_id'] = $id;
                $queue['tasks'][$index]['last_session_id'] = $id;
            } else {
                $session = $this->ownedSession($id, $head, $client);
                if ($name === 'claim_task') {
                    wf_require($session['status'] === 'active', 'The session is already closed.', 'session_closed');
                    $index = $this->taskIndex($queue, $args['task_id']); $this->available($queue, $index, $id);
                    if (in_array($args['task_id'], $session['task_ids'], true)) { return $this->receipt($snapshot, $client, $session) + ['replayed' => true]; }
                    $session['task_ids'][] = $args['task_id'];
                    $queue['tasks'][$index]['status'] = 'in_progress'; $queue['tasks'][$index]['owner_session_id'] = $id;
                    $queue['tasks'][$index]['last_session_id'] = $id;
                } else {
                    $fingerprint = hash('sha256', wf_json([$args['outcome'], $args['summary'], $args['next_action'], $args['changed_files'], $args['checks'], $args['evidence_urls'] ?? []]));
                    if ($session['status'] !== 'active') {
                        wf_require(($session['finish_fingerprint'] ?? '') === $fingerprint, 'A closed session cannot be overwritten with another handoff.', 'session_closed');
                        return $this->receipt($snapshot, $client, $session) + ['replayed' => true];
                    }
                    $session['status'] = $args['outcome']; $session['ended_at'] = wf_now();
                    $session['summary'] = $args['summary']; $session['next_action'] = $args['next_action'];
                    $session['changed_files'] = array_values(array_unique($args['changed_files'])); $session['checks'] = $args['checks'];
                    $session['evidence_urls'] = $args['evidence_urls'] ?? []; $session['finish_fingerprint'] = $fingerprint;
                    foreach ($session['task_ids'] as $taskId) {
                        $index = $this->taskIndex($queue, $taskId);
                        wf_require($queue['tasks'][$index]['owner_session_id'] === $id && $queue['tasks'][$index]['status'] === 'in_progress', 'The shared task claim changed; refresh before finishing.', 'task_conflict');
                        $queue['tasks'][$index]['status'] = $args['outcome'] === 'completed' ? 'done' : 'blocked';
                        $queue['tasks'][$index]['owner_session_id'] = null; $queue['tasks'][$index]['last_session_id'] = $id;
                        $queue['tasks'][$index]['next_action'] = $args['next_action'];
                        $queue['tasks'][$index]['evidence'] = array_values(array_unique(array_merge($queue['tasks'][$index]['evidence'], $session['evidence_urls'])));
                    }
                }
            }
            $queue['updated_at'] = wf_now();
            $files = [$sessionPath => wf_json($session), WorkflowGitHub::PREFIX . 'tasks.json' => wf_json($queue),
                WorkflowGitHub::PREFIX . 'CURRENT_STATUS.md' => wf_render($snapshot['state'], $queue)];
            try {
                $commit = $this->github->publish($head, $files, 'Record AI workflow ' . $name . ' for ' . $id);
                return $this->receipt($snapshot, $client, $session, $commit) + ['replayed' => false];
            } catch (WorkflowError $e) {
                if ($e->kind !== 'ref_conflict') { throw $e; }
                if ($this->github->head() === $head) { throw new WorkflowError('github_access', 'GitHub refused a non-forced update. Check repository rules and service-token write permission.'); }
            }
        }
        throw new WorkflowError('ref_conflict', 'The record changed repeatedly. Refresh and retry with the same request_id.');
    }

    private function history(array $args, array $client): array
    {
        $snapshot = $this->github->snapshot(); $paths = [];
        foreach ($this->github->tree($snapshot['head']) as $entry) {
            if (preg_match('~^docs/ai-workflow/sessions/([a-z0-9][a-z0-9_-]{0,95})\.json$~D', $entry['path'], $match)) {
                wf_require($entry['mode'] === '100644' && $entry['type'] === 'blob', 'Unsafe history record.', 'invalid_record');
                $paths[$match[1]] = $entry['path'];
            }
        }
        // Stable filename pagination; records retain their actual started_at/ended_at.
        krsort($paths); $ids = array_keys($paths); $offset = 0;
        if (isset($args['cursor'])) {
            $position = array_search($args['cursor'], $ids, true);
            wf_require($position !== false, 'History cursor is not present; restart pagination.'); $offset = $position + 1;
        }
        $selected = array_slice($ids, $offset, $args['limit'] ?? 10); $sessions = [];
        foreach ($selected as $id) { $sessions[] = $this->github->read($paths[$id], $snapshot['head']); }
        return $this->receipt($snapshot, $client) + ['sessions' => $sessions,
            'next_cursor' => $offset + count($selected) < count($ids) ? end($selected) : null,
            'order' => 'session_id_descending; use recorded timestamps for chronology',
            'github_baseline' => $this->github->read(WorkflowGitHub::PREFIX . 'history/github-baseline.json', $snapshot['head'])];
    }
}

function wf_serve(MirroriedWorkflowServer $server): void
{
    $headers = function_exists('getallheaders') ? getallheaders() : [];
    foreach ($_SERVER as $key => $value) {
        if (str_starts_with($key, 'HTTP_')) { $headers[str_replace('_', '-', strtolower(substr($key, 5)))] = $value; }
    }
    $headers['content-type'] = $_SERVER['CONTENT_TYPE'] ?? ($headers['Content-Type'] ?? '');
    $body = file_get_contents('php://input', false, null, 0, 131073);
    [$status, $response] = $server->handle($_SERVER['REQUEST_METHOD'] ?? 'GET', $headers, $body === false ? '' : $body);
    http_response_code($status);
    if ($status === 401) { header('WWW-Authenticate: Bearer realm="mirroried-led-workflow"'); }
    if ($status === 405) { header('Allow: POST'); }
    if ($response !== null) { header('Content-Type: application/json; charset=utf-8'); echo wf_json($response); }
}
