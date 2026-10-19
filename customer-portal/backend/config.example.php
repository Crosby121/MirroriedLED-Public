<?php
declare(strict_types=1);

/* Copy to ../mirroriedled-private/customer-portal/config.php OUTSIDE public_html.
 * This example has no credentials. Premium limits are drafts; product checkout is disabled.
 * Never place your working configuration, database, sessions or media in public_html.
 */
return [
    'business_enabled' => true,
    'premium_enabled' => false, // Premium media remains closed during the two-product opening.
    'commerce' => [
        'enabled' => false,
        'mode' => 'live', // Use test only for provider sandbox acceptance, never fulfillment.
        'stripe_secret_key' => getenv('MLED_STRIPE_SECRET_KEY') ?: '',
        'stripe_webhook_secret' => getenv('MLED_STRIPE_WEBHOOK_SECRET') ?: '',
        // Set after the merchant's actual registrations, product taxability,
        // shipping policy, proof process and production capacity are confirmed.
        'tax_setup_confirmed' => false,
        'fulfillment_setup_confirmed' => false,
    ],
    // Owner-approved numeric account IDs only. Verify each account before assigning roles.
    // Never assign staff access by an unverified email or by a signup form field.
    'staff_users' => [], // Example after verification: 7 => ['admin'].
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
    'infinity_builder' => [
        // Private, owner-approved activation only. No key is sent to the browser.
        'ai_enabled' => false,
        'openai_api_key' => '',
        'allowed_user_ids' => [],
        'text_model' => 'gpt-4o-mini',
        'image_model' => 'gpt-image-1.5',
        'daily_images_per_user' => 3,
        'daily_images_total' => 10,
    ],
];
