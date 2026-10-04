<?php
declare(strict_types=1);

ini_set('display_errors', '0');
require __DIR__ . '/portal.php';

header('Cache-Control: no-store, private');
header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: same-origin');
header('X-Frame-Options: DENY');

try {
    $portal = new CustomerPortal();
    $portal->handle();
} catch (PortalError $error) {
    portal_json(['ok' => false, 'error' => $error->getMessage()], $error->httpStatus);
} catch (Throwable $error) {
    error_log('Mirroried LED customer portal request failed: ' . get_class($error));
    portal_json(['ok' => false, 'error' => 'The portal could not complete this request. Please try again.'], 500);
}
