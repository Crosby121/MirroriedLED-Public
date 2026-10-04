<?php
declare(strict_types=1);

/* Copy to ../mirroriedled-private/customer-portal/config.php OUTSIDE public_html.
 * This example has no credentials. Limits are drafts; billing is disabled.
 * Never place your working configuration, database, sessions or media in public_html.
 */
return [
    'storage_path' => __DIR__ . '/storage',
    'origin' => 'https://mirroriedled.com',
    'allow_insecure_localhost' => false,
    'session_idle_seconds' => 7200,
    'session_lifetime_seconds' => 43200,
    'max_audio_bytes' => 64 * 1024 * 1024,
    'max_video_bytes' => 128 * 1024 * 1024,
    'plans' => [
        'free' => ['songs' => 3, 'videos' => 1, 'bytes' => 256 * 1024 * 1024],
        'premium' => ['songs' => 25, 'videos' => 5, 'bytes' => 2 * 1024 * 1024 * 1024],
        'premium-plus' => ['songs' => 100, 'videos' => 20, 'bytes' => 8 * 1024 * 1024 * 1024],
    ],
    'auth_limits' => [
        'login_ip' => 50,
        'login_email' => 10,
        'signup_ip' => 10,
        'window_seconds' => 900,
    ],
];
