<?php
declare(strict_types=1);
ini_set('display_errors','0');
set_error_handler(static function (): never { throw new RuntimeException('Sandbox verification prerequisite unavailable'); });

/* CLI-only additive schema check. Never install this helper under public_html. */
function engraving_path(string $path, bool $directory=false, bool $private=false): void
{
    clearstatcache(true,$path);
    for($p=$path;$p!==dirname($p);$p=dirname($p))if(is_link($p))throw new RuntimeException('Unsafe path');
    $s=lstat($path);
    if(!$s||($directory?!is_dir($path):!is_file($path))||$s['uid']!==posix_geteuid()||($s['mode']&($private?0077:0022))!==0||(!$directory&&$s['nlink']!==1))throw new RuntimeException('Unsafe ownership or permissions');
}

function engraving_snapshot(PDO $db,array $tables): string
{
    $snapshot=[];
    foreach($tables as $table){
        if(!preg_match('/^[a-z_]+$/D',$table))throw new RuntimeException('Unexpected table');
        $snapshot[$table]=$db->query('SELECT * FROM "'.$table.'"')->fetchAll();
    }
    return hash('sha256',serialize($snapshot));
}

try {
    $root=$argv[1]??'';$fingerprint=$argv[2]??'';
    if(PHP_SAPI!=='cli'||!preg_match('/^[a-f0-9]{64}$/D',$fingerprint)||basename($root)!=='public_html'||basename(dirname($root))!=='mirroriedled.com'||realpath($root)!==$root)throw new RuntimeException('Isolated sandbox required');
    engraving_path($root,true);engraving_path(dirname($root),true);
    $private=dirname($root).'/mirroriedled-private/checkout-sandbox';
    engraving_path(dirname($private),true);engraving_path($private,true,true);
    foreach(['config.php','receipt.json'] as $file)engraving_path($private.'/'.$file,false,true);
    $configHash=hash_file('sha256',$private.'/config.php');
    $receipt=json_decode(file_get_contents($private.'/receipt.json'),true,32,JSON_THROW_ON_ERROR);
    $backend=$root.'/MLED_checkout_TEST/customer-portal/backend';
    foreach(['portal.php','business.php','commerce.php','builder.php','api.php'] as $file){
        engraving_path($backend.'/'.$file);
        if(hash_file('sha256',$backend.'/'.$file)!==($receipt['public_hashes']['customer-portal/backend/'.$file]??null))throw new RuntimeException('Reviewed backend required');
    }
    if(!str_contains(file_get_contents($backend.'/api.php'),'/mirroriedled-private/checkout-sandbox/config.php'))throw new RuntimeException('Isolated API required');
    $config=require $private.'/config.php';
    if(($config['commerce']['mode']??null)!=='test'||($config['commerce']['enabled']??null)!==true||!preg_match('/^rk_test_[A-Za-z0-9]+$/D',$config['commerce']['stripe_secret_key']??'')||($config['staff_users']??null)!==[]||($config['storage_path']??null)!==$private.'/storage')throw new RuntimeException('Existing isolated test configuration required');
    engraving_path($private.'/storage',true,true);engraving_path($private.'/storage/portal.sqlite',false,true);engraving_path($private.'/storage/business-files',true,true);
    require $backend.'/portal.php';
    $db=new PDO('sqlite:'.$private.'/storage/portal.sqlite',null,null,[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC]);
    $db->exec('BEGIN IMMEDIATE');
    try {
        $tables=$db->query("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")->fetchAll(PDO::FETCH_COLUMN);
        $before=engraving_snapshot($db,$tables);
        $orders=array_values(array_filter($db->query('SELECT * FROM business_orders')->fetchAll(),static fn($o)=>hash('sha256',$o['id'])===$fingerprint));
        if(count($orders)!==1||$orders[0]['status']!=='APPROVED'||$orders[0]['approved_proof_id']!==$orders[0]['proof_id'])throw new RuntimeException('Original approved test order required');
        $order=$orders[0];$q=$db->prepare('SELECT * FROM users WHERE id=?');$q->execute([$order['user_id']]);$user=$q->fetch();
        if(!$user)throw new RuntimeException('Existing owner required');
        $service=new BusinessPortal($db,$config,$private.'/storage',$user);
        $public=(new ReflectionMethod(BusinessPortal::class,'publicOrder'))->invoke($service,$order);
        if($public['engravingApprovalRequired']!==true||$public['engravingReview']!==null||engraving_snapshot($db,$tables)!==$before||hash_file('sha256',$private.'/config.php')!==$configHash)throw new RuntimeException('Preserved records and unapproved engraving required');
        $q=$db->prepare('SELECT COUNT(*) FROM commerce_engraving_prices WHERE order_id=?');$q->execute([$order['id']]);
        if((int)$q->fetchColumn()!==0||$public['commerce']['installments']!==null)throw new RuntimeException('Original full-payment test terms must remain unchanged');
        $db->exec('COMMIT');
    }catch(Throwable $error){$db->exec('ROLLBACK');throw $error;}
    echo json_encode(['engraving_schema_verified'=>true,'staged_payment_schema_verified'=>true,'legacy_full_payment_preserved'=>true,'existing_private_records_preserved'=>true,'customer_engraving_approval_created'=>false,'production_payment_activation'=>false],JSON_THROW_ON_ERROR).PHP_EOL;
}catch(Throwable){fwrite(STDERR,"Sandbox engraving verification stopped; inspect private prerequisites. No customer approval or production activation performed.\n");exit(1);}
