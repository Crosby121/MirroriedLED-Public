<?php
declare(strict_types=1);
/* CLI-only preservation guard. Keep helper and receipts outside public_html. */
ini_set('display_errors','0');
set_error_handler(static function (): never { throw new RuntimeException('Release prerequisite unavailable'); });

function quote_path(string $path,bool $directory=false,bool $private=false): void
{
    for($p=$path;$p!==dirname($p);$p=dirname($p))if(is_link($p))throw new RuntimeException('Unsafe path');
    $s=lstat($path);
    if(!$s||($directory?!is_dir($path):!is_file($path))||$s['uid']!==posix_geteuid()||($s['mode']&($private?0077:0022))!==0||(!$directory&&$s['nlink']!==1))throw new RuntimeException('Unsafe ownership or permissions');
}

function quote_store(string $private,bool $production): array
{
    quote_path($private,true,true);quote_path($private.'/config.php',false,true);
    $config=require $private.'/config.php';
    if($production&&(($config['commerce']['enabled']??false)!==false||($config['business_enabled']??false)!==true||($config['premium_enabled']??false)!==false))throw new RuntimeException('Quote-only production required');
    $storage=$config['storage_path']??'';
    if($storage!==$private.'/storage'||realpath($storage)!==$storage)throw new RuntimeException('Existing private storage required');
    quote_path($storage,true,true);quote_path($storage.'/portal.sqlite',false,true);
    $db=new PDO('sqlite:'.$storage.'/portal.sqlite',null,null,[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC]);
    $db->exec('PRAGMA query_only=ON; PRAGMA busy_timeout=5000; BEGIN');
    try{
        $tables=[];
        foreach($db->query("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")->fetchAll(PDO::FETCH_COLUMN) as $name){
            if(!preg_match('/^[A-Za-z_][A-Za-z0-9_]*$/D',$name))throw new RuntimeException('Unexpected schema');
            $rows=[];foreach($db->query('SELECT * FROM "'.$name.'"')->fetchAll() as $row)$rows[]=hash('sha256',serialize($row));
            sort($rows);$tables[$name]=$rows;
        }
        $db->exec('COMMIT');
    }catch(Throwable $error){$db->exec('ROLLBACK');throw $error;}
    $files=[];
    foreach(new RecursiveIteratorIterator(new RecursiveDirectoryIterator($storage,FilesystemIterator::SKIP_DOTS)) as $file){
        $name=substr($file->getPathname(),strlen($storage)+1);
        if(str_starts_with($name,'sessions/')||in_array($name,['portal.sqlite','portal.sqlite-wal','portal.sqlite-shm','portal.sqlite-journal'],true))continue;
        quote_path($file->getPathname(),false,true);$files[$name]=hash_file('sha256',$file->getPathname());
    }
    ksort($files);
    return ['config'=>hash_file('sha256',$private.'/config.php'),'tables'=>$tables,'files'=>$files];
}

try{
    [$script,$action,$root,$receipt,$release]=array_pad($argv,5,'');
    if(PHP_SAPI!=='cli'||!in_array($action,['before','after'],true)||!preg_match('/^[a-f0-9]{40}$/D',$release)||basename($root)!=='public_html'||basename(dirname($root))!=='mirroriedled.com'||realpath($root)!==$root)throw new RuntimeException('Exact website release required');
    quote_path($root,true);quote_path(dirname($root),true);
    $stage=dirname($receipt);
    if(dirname($stage)!==dirname($root)||!preg_match('/^\.mirroriedled-release-[0-9]+-[0-9]+$/D',basename($stage))||basename($receipt)!=='private-preservation.json')throw new RuntimeException('Private release receipt required');
    quote_path($stage,true,true);
    $private=dirname($root).'/mirroriedled-private';quote_path($private,true);
    $stores=['customer-portal'=>quote_store($private.'/customer-portal',true),'checkout-sandbox'=>quote_store($private.'/checkout-sandbox',false)];
    if($action==='before'){
        $handle=fopen($receipt,'x');if($handle===false)throw new RuntimeException('Exclusive receipt required');
        chmod($receipt,0600);fwrite($handle,json_encode(['root'=>$root,'release'=>$release,'stores'=>$stores],JSON_THROW_ON_ERROR));fclose($handle);
    }else{
        quote_path($receipt,false,true);$before=json_decode(file_get_contents($receipt),true,64,JSON_THROW_ON_ERROR);
        if(($before['root']??null)!==$root||($before['release']??null)!==$release)throw new RuntimeException('Matching release receipt required');
        foreach($before['stores'] as $name=>$old){
            $current=$stores[$name]??[];
            if(($current['config']??null)!==$old['config'])throw new RuntimeException('Private configuration changed');
            foreach($old['tables'] as $table=>$rows){
                $counts=array_count_values($current['tables'][$table]??[]);
                foreach(array_count_values($rows) as $row=>$count)if(($counts[$row]??0)<$count)throw new RuntimeException('Private records changed');
            }
            foreach($old['files'] as $file=>$hash)if(($current['files'][$file]??null)!==$hash)throw new RuntimeException('Private artwork changed');
        }
    }
    echo json_encode(['quote_only_private_preflight'=>true,'production_payments_disabled'=>true,'private_records_preserved'=>$action==='after'],JSON_THROW_ON_ERROR).PHP_EOL;
}catch(Throwable){fwrite(STDERR,"Quote-only release preservation stopped; inspect private prerequisites.\n");exit(1);}
