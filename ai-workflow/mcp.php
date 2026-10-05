<?php
declare(strict_types=1);

ini_set('display_errors', '0');
header('Cache-Control: no-store, private');
header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: no-referrer');

// On Hostinger, this directory is alongside public_html, never inside it.
$private = getenv('MIRRORIED_WORKFLOW_PRIVATE_DIR') ?: dirname(__DIR__, 2) . '/mirroriedled-private/ai-workflow';
try {
    if (!is_file($private . '/server.php') || !is_file($private . '/config.json')) {
        http_response_code(503);
        header('Content-Type: application/json');
        echo '{"error":"The shared workflow connector is not configured."}';
        exit;
    }
    require $private . '/server.php';
    $config = json_decode(file_get_contents($private . '/config.json'), true, 64, JSON_THROW_ON_ERROR);
    wf_serve(new MirroriedWorkflowServer($config));
} catch (Throwable $error) {
    error_log('Mirroried LED workflow request failed: ' . get_class($error));
    http_response_code(503);
    header('Content-Type: application/json');
    echo '{"error":"The workflow connector could not complete this request. Check its private configuration and retry."}';
}
