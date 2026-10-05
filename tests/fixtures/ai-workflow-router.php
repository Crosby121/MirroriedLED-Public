<?php
declare(strict_types=1);

// Local integration fixture, never part of the deployment package.
ini_set('display_errors', '0');
require dirname(__DIR__, 2) . '/services/ai-workflow/server.php';
$config = json_decode(file_get_contents(getenv('WF_TEST_CONFIG')), true, 64, JSON_THROW_ON_ERROR);
$transport = function(string $method, string $path, ?array $body): array {
    $curl = curl_init(getenv('WF_TEST_GITHUB') . $path);
    curl_setopt_array($curl, [CURLOPT_RETURNTRANSFER => true, CURLOPT_CUSTOMREQUEST => $method,
        CURLOPT_TIMEOUT => 10, CURLOPT_HTTPHEADER => ['Content-Type: application/json']]);
    if ($body !== null) { curl_setopt($curl, CURLOPT_POSTFIELDS, wf_json($body)); }
    $raw = curl_exec($curl); $status = curl_getinfo($curl, CURLINFO_HTTP_CODE); curl_close($curl);
    if ($status === 409 || $status === 422) { throw new WorkflowError('ref_conflict', 'GitHub refused the branch update.'); }
    if ($status < 200 || $status >= 300) { throw new WorkflowError('github_access', 'GitHub access failed.'); }
    return json_decode($raw, true, 64, JSON_THROW_ON_ERROR);
};
try { wf_serve(new MirroriedWorkflowServer($config, new WorkflowGitHub($config, $transport))); }
catch (Throwable $e) { http_response_code(500); echo '{"error":"Fixture request failed."}'; }
