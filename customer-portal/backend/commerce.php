<?php
declare(strict_types=1);

/** Physical-product checkout. A browser redirect never proves payment. */
final class CommercePortal
{
    public const READS = ['commerce-orders'];
    public const WRITES = ['commerce-address', 'commerce-offer', 'commerce-checkout', 'commerce-refresh'];
    public const PRODUCTS = ['Custom Infinity Mirror', 'Address Sign or Mailbox'];
    public function __construct(private PDO $db, private array $config, private ?array $user, private ?Closure $transport=null)
    {
        self::migrate($db);
    }
    public static function migrate(PDO $db): void
    {
        $db->exec(<<<'SQL'
        CREATE TABLE IF NOT EXISTS commerce_addresses(order_id TEXT PRIMARY KEY REFERENCES business_orders(id), address TEXT NOT NULL, updated_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS commerce_offers(order_id TEXT PRIMARY KEY REFERENCES business_orders(id), proof_id TEXT NOT NULL, version INTEGER NOT NULL, terms TEXT NOT NULL, created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS commerce_offer_history(order_id TEXT NOT NULL REFERENCES business_orders(id), version INTEGER NOT NULL, terms TEXT NOT NULL, PRIMARY KEY(order_id,version));
        CREATE TABLE IF NOT EXISTS commerce_checkouts(
            id INTEGER PRIMARY KEY, order_id TEXT NOT NULL REFERENCES business_orders(id), offer_version INTEGER NOT NULL,
            attempt INTEGER NOT NULL, snapshot TEXT NOT NULL, provider_id TEXT UNIQUE, url TEXT, expires_at INTEGER,
            state TEXT NOT NULL DEFAULT 'creating', payment_intent TEXT, paid_cents INTEGER, tax_cents INTEGER,
            created_at INTEGER NOT NULL, paid_at INTEGER, UNIQUE(order_id,offer_version,attempt)
        );
        CREATE TABLE IF NOT EXISTS commerce_webhooks(event_id TEXT PRIMARY KEY, processed_at INTEGER NOT NULL);
        SQL);
    }
    public static function available(array $config): bool
    {
        $c=$config['commerce']??[];
        $mode=$c['mode']??'live';
        return ($config['business_enabled']??false)===true && ($c['enabled']??false)===true && in_array($mode,['live','test'],true)
            && preg_match('/^sk_'.$mode.'_[A-Za-z0-9]+$/D',(string)($c['stripe_secret_key']??''))===1
            && preg_match('/^whsec_[A-Za-z0-9]+$/D',(string)($c['stripe_webhook_secret']??''))===1
            && ($c['tax_setup_confirmed']??false)===true && ($c['fulfillment_setup_confirmed']??false)===true && extension_loaded('curl');
    }
    private function rows(string $sql,array $params=[]): array { $q=$this->db->prepare($sql);$q->execute($params);return $q->fetchAll(); }
    private function exec(string $sql,array $params=[]): void { $q=$this->db->prepare($sql);$q->execute($params); }
    private function order(mixed $id,bool $staff=false): array
    {
        if (!is_string($id)||!preg_match('/^MLED-[a-f0-9]{20}$/D',$id)) throw new PortalError('Order not found.',404);
        $row=$this->rows('SELECT * FROM business_orders WHERE id=?',[$id])[0]??null;
        if (!$row||(!$staff&&(int)$row['user_id']!==(int)($this->user['id']??0))) throw new PortalError('Order not found.',404);
        $items=json_decode($row['configuration'],true,32,JSON_THROW_ON_ERROR);
        foreach ($items as $item) if (!in_array($item['product'],self::PRODUCTS,true)) throw new PortalError('Online checkout is available for Infinity Mirrors and address signs.',403);
        return $row;
    }
    private function staff(): void
    {
        if (!$this->user||!array_intersect(BusinessPortal::roles($this->config,$this->user),['admin','sales'])) throw new PortalError('Authorized sales access is required.',403);
    }
    private static function integer(mixed $v,int $min,int $max): int
    {
        if (!is_int($v)||$v<$min||$v>$max) throw new PortalError('Enter a valid price or number of days.',422);
        return $v;
    }
    public static function address(mixed $input): array
    {
        if (!is_array($input)) throw new PortalError('Complete your delivery address.',422);
        $out=[];
        foreach (['name'=>120,'line1'=>180,'line2'=>180,'city'=>100,'state'=>2,'postalCode'=>10] as $key=>$max) {
            $v=$input[$key]??'';
            if (!is_string($v)||strlen(trim($v))>$max||preg_match('/[\x00-\x1F\x7F]/',$v)||($key!=='line2'&&trim($v)==='')) throw new PortalError('Complete each delivery address field.',422);
            $out[$key]=trim($v);
        }
        $out['state']=strtoupper($out['state']);
        $states=explode(' ','AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY');
        if (($input['country']??'')!=='US'||!in_array($out['state'],$states,true)||!preg_match('/^\d{5}(?:-\d{4})?$/D',$out['postalCode'])) throw new PortalError('Use a supported United States delivery address.',422);
        return $out+['country'=>'US'];
    }
    public static function validateAddressBuild(mixed $input): array
    {
        if (!is_array($input)||($input['version']??null)!==1) throw new PortalError('Check your address-sign configuration.',422);
        $choices=['size'=>['12×6','18×8','24×10'],'finish'=>['Matte black','White','Natural birch'],'mount'=>['Wall mount','Post mount'],'lighting'=>['Steady glow','Addressable effects'],'font'=>['Modern','Classic'],'color'=>['Warm white','Cool white','Turquoise','Blue','Purple']];
        $out=['version'=>1];
        foreach ($choices as $key=>$values) { if (!in_array($input[$key]??null,$values,true)) throw new PortalError('Choose a supported address-sign option.',422);$out[$key]=$input[$key]; }
        foreach (['number'=>12,'street'=>60] as $key=>$max) {
            $v=$input[$key]??'';
            if (!is_string($v)||strlen(trim($v))>$max||preg_match('/[\x00-\x1F\x7F]/',$v)||($key==='number'&&(!preg_match('/^[A-Za-z0-9 -]{1,12}$/D',trim($v))))) throw new PortalError('Enter your address number and optional street name within their limits.',422);
            $out[$key]=trim($v);
        }
        return $out;
    }
    public static function locked(PDO $db,string $id): bool
    {
        self::migrate($db);$q=$db->prepare("SELECT 1 FROM commerce_checkouts WHERE order_id=? AND state IN ('creating','open','paid','review') LIMIT 1");$q->execute([$id]);return $q->fetchColumn()!==false;
    }
    public static function publicTerms(PDO $db,string $id): array
    {
        self::migrate($db);
        $q=$db->prepare('SELECT terms FROM commerce_offers WHERE order_id=?');$q->execute([$id]);$terms=$q->fetchColumn();
        $q=$db->prepare('SELECT address FROM commerce_addresses WHERE order_id=?');$q->execute([$id]);$address=$q->fetchColumn();
        $q=$db->prepare('SELECT state,paid_cents,tax_cents,paid_at,expires_at FROM commerce_checkouts WHERE order_id=? ORDER BY id DESC LIMIT 1');$q->execute([$id]);$payment=$q->fetch()?:null;
        return ['offer'=>$terms===false?null:json_decode($terms,true,16,JSON_THROW_ON_ERROR),'address'=>$address===false?null:json_decode($address,true,16,JSON_THROW_ON_ERROR),'payment'=>$payment];
    }
    public function handle(string $action,array $data): never
    {
        $result=match($action) {
            'commerce-orders'=>$this->orders(),
            'commerce-address'=>$this->saveAddress($data),
            'commerce-offer'=>$this->offer($data),
            'commerce-checkout'=>$this->checkout($data),
            'commerce-refresh'=>$this->refresh($data),
            default=>throw new PortalError('Checkout action unavailable.',404),
        };
        portal_json(['ok'=>true]+$result);
    }
    private function orders(): array
    {
        $rows=$this->rows('SELECT id FROM business_orders WHERE user_id=? ORDER BY created_at DESC LIMIT 200',[$this->user['id']]);
        return ['commerce'=>array_map(fn($r)=>['orderId'=>$r['id']]+self::publicTerms($this->db,$r['id']),$rows)];
    }
    private function saveAddress(array $data): array
    {
        $order=$this->order($data['orderId']??null);$address=self::address($data['address']??null);
        $this->db->exec('BEGIN IMMEDIATE');
        try {
            if (self::locked($this->db,$order['id'])||!in_array($order['status'],['REQUESTED','QUOTED','APPROVED'],true)) throw new PortalError('Delivery details are locked for this checkout or order. Contact support to make a change.',409);
            $existing=self::publicTerms($this->db,$order['id'])['address'];
            $this->exec('INSERT INTO commerce_addresses(order_id,address,updated_at) VALUES(?,?,?) ON CONFLICT(order_id) DO UPDATE SET address=excluded.address,updated_at=excluded.updated_at',[$order['id'],json_encode($address,JSON_THROW_ON_ERROR),time()]);
            if ($existing!==$address) $this->exec('DELETE FROM commerce_offers WHERE order_id=?',[$order['id']]);
            $this->db->exec('COMMIT');
        } catch(Throwable $e) { $this->db->exec('ROLLBACK');throw $e; }
        return ['commerce'=>self::publicTerms($this->db,$order['id'])];
    }
    private function offer(array $data): array
    {
        $this->staff();$this->db->exec('BEGIN IMMEDIATE');
        try {
            $order=$this->order($data['orderId']??null,true);
            if (!in_array($order['status'],['QUOTED','APPROVED'],true)||($data['proofId']??null)!==$order['proof_id']||self::locked($this->db,$order['id'])) throw new PortalError('Publish the latest proof and quote before setting checkout terms. Active checkouts are locked.',409);
            $address=self::publicTerms($this->db,$order['id'])['address'];if (!$address) throw new PortalError('The customer must save a delivery address before shipping can be quoted.',422);
            if (($data['fulfillmentConfirmed']??false)!==true) throw new PortalError('Confirm material availability, the delivered shipping price and production capacity.',422);
            $shipping=self::integer($data['shippingCents']??null,0,10000000);
            $pMin=self::integer($data['productionMinDays']??null,1,365);$pMax=self::integer($data['productionMaxDays']??null,$pMin,365);
            $tMin=self::integer($data['transitMinDays']??null,1,60);$tMax=self::integer($data['transitMaxDays']??null,$tMin,60);
            $expires=self::integer($data['validDays']??7,1,30);
            $version=(int)$this->rows('SELECT COALESCE(MAX(version),0)+1 AS version FROM commerce_offer_history WHERE order_id=?',[$order['id']])[0]['version'];
            $product=self::integer((int)$order['quote_cents'],50,100000000);
            $terms=['version'=>$version,'proofId'=>$order['proof_id'],'productCents'=>$product,'shippingCents'=>$shipping,'beforeTaxCents'=>$product+$shipping,'currency'=>'USD',
                'productionMinDays'=>$pMin,'productionMaxDays'=>$pMax,'transitMinDays'=>$tMin,'transitMaxDays'=>$tMax,'expiresAt'=>time()+$expires*86400,'address'=>$address,
                'productionStarts'=>'After payment confirmation and approval of the final artwork proof. Estimates use business days.','tax'=>'Final tax and total are calculated and shown in secure checkout before payment.'];
            $this->exec('INSERT INTO commerce_offers(order_id,proof_id,version,terms,created_at) VALUES(?,?,?,?,?) ON CONFLICT(order_id) DO UPDATE SET proof_id=excluded.proof_id,version=excluded.version,terms=excluded.terms,created_at=excluded.created_at',[$order['id'],$order['proof_id'],$version,json_encode($terms,JSON_THROW_ON_ERROR),time()]);
            $this->exec('INSERT INTO commerce_offer_history(order_id,version,terms) VALUES(?,?,?)',[$order['id'],$version,json_encode($terms,JSON_THROW_ON_ERROR)]);
            $this->event($order,'CHECKOUT_OFFER','Your complete product and shipping quote, production estimate and secure checkout terms are ready.');
            $this->db->exec('COMMIT');
        } catch(Throwable $e) { $this->db->exec('ROLLBACK');throw $e; }
        return ['commerce'=>self::publicTerms($this->db,$order['id'])];
    }
    private function event(array $order,string $kind,string $message): void
    {
        $this->exec('INSERT INTO business_events(order_id,actor_id,kind,detail,customer_message,created_at) VALUES(?,?,?,?,?,?)',[$order['id'],$this->user['id']??$order['user_id'],$kind,'{}',$message,time()]);
    }
    private function stripe(string $method,string $path,array $params=[],?string $key=null): array
    {
        if (!self::available($this->config)) throw new PortalError('Online payment is awaiting the business payment connection. No payment has been taken.',503);
        // Dependency injection is used only by server-side acceptance tests.
        // No request, environment variable or private config can select a transport.
        if ($this->transport!==null) return ($this->transport)($method,$path,$params,$key);
        $url='https://api.stripe.com/v1'.$path;
        if ($method==='GET'&&$params) $url.='?'.http_build_query($params);
        $curl=curl_init($url);$headers=['Authorization: Bearer '.$this->config['commerce']['stripe_secret_key']];
        if ($key!==null) $headers[]='Idempotency-Key: '.$key;
        curl_setopt_array($curl,[CURLOPT_RETURNTRANSFER=>true,CURLOPT_CUSTOMREQUEST=>$method,CURLOPT_HTTPHEADER=>$headers,CURLOPT_CONNECTTIMEOUT=>10,CURLOPT_TIMEOUT=>30,CURLOPT_SSL_VERIFYPEER=>true,CURLOPT_SSL_VERIFYHOST=>2,CURLOPT_FOLLOWLOCATION=>false]);
        if ($method==='POST') curl_setopt($curl,CURLOPT_POSTFIELDS,http_build_query($params));
        $body=curl_exec($curl);$status=curl_getinfo($curl,CURLINFO_RESPONSE_CODE);curl_close($curl);
        if ($body===false||$status<200||$status>=300) throw new PortalError('The payment service could not complete this step. Your order is saved; try again or contact support.',502);
        try { $decoded=json_decode($body,true,64,JSON_THROW_ON_ERROR); } catch(Throwable) { throw new PortalError('The payment service returned an unreadable response.',502); }
        if (!is_array($decoded)) throw new PortalError('Payment service unavailable.',502);
        return $decoded;
    }
    private function checkout(array $data): array
    {
        if (!self::available($this->config)) throw new PortalError('Online payment is awaiting the business payment connection. No payment has been taken.',503);
        $this->db->exec('BEGIN IMMEDIATE');
        try {
            $order=$this->order($data['orderId']??null);$terms=self::publicTerms($this->db,$order['id'])['offer'];
            if (!$terms||$terms['expiresAt']<time()||$terms['proofId']!==$order['proof_id']||$order['approved_proof_id']!==$order['proof_id']||$order['status']!=='APPROVED'||($data['acceptTerms']??false)!==true||($data['offerVersion']??null)!==$terms['version']) throw new PortalError('Approve the current artwork proof and review the latest quote, delivery estimate and checkout terms.',409);
            $prior=$this->rows('SELECT * FROM commerce_checkouts WHERE order_id=? AND offer_version=? ORDER BY attempt DESC LIMIT 1',[$order['id'],$terms['version']])[0]??null;
            if ($prior&&in_array($prior['state'],['paid','review'],true)) throw new PortalError('This order already has a payment record. Review it in your account.',409);
            if ($prior&&$prior['state']==='open'&&$prior['expires_at']>time()) { $this->db->exec('COMMIT');return ['checkoutUrl'=>$prior['url'],'orderId'=>$order['id']]; }
            if ($prior&&$prior['state']==='open') throw new PortalError('Refresh payment status before trying checkout again.',409);
            if ($prior&&$prior['state']==='creating') $row=$prior;
            else {
                $attempt=$prior?(int)$prior['attempt']+1:1;$snapshot=$terms+['orderId'=>$order['id'],'userId'=>(int)$this->user['id'],'email'=>$this->user['email'],'mode'=>$this->config['commerce']['mode']??'live'];
                $this->exec('INSERT INTO commerce_checkouts(order_id,offer_version,attempt,snapshot,created_at) VALUES(?,?,?,?,?)',[$order['id'],$terms['version'],$attempt,json_encode($snapshot,JSON_THROW_ON_ERROR),time()]);
                $row=$this->rows('SELECT * FROM commerce_checkouts WHERE id=?',[$this->db->lastInsertId()])[0];
            }
            $this->db->exec('COMMIT');
        } catch(Throwable $e) { if ($this->db->inTransaction()) $this->db->exec('ROLLBACK');else { try {$this->db->exec('ROLLBACK');}catch(Throwable){} }throw $e; }
        $s=json_decode($row['snapshot'],true,32,JSON_THROW_ON_ERROR);$a=$s['address'];$origin=$this->config['origin'];
        $basePath=rtrim(dirname(dirname(dirname((string)($_SERVER['SCRIPT_NAME']??'/customer-portal/backend/api.php')))),'/');
        $params=['mode'=>'payment','payment_method_types'=>['card'],'customer_email'=>$s['email'],'client_reference_id'=>$s['orderId'],'automatic_tax'=>['enabled'=>'true'],
            'line_items'=>[['price_data'=>['currency'=>'usd','unit_amount'=>$s['productCents'],'tax_behavior'=>'exclusive','product_data'=>['name'=>'Mirroried LED custom build '.$s['orderId'],'tax_code'=>'txcd_99999999']], 'quantity'=>1]],
            'shipping_options'=>[['shipping_rate_data'=>['type'=>'fixed_amount','display_name'=>'Delivery to '.$a['city'].', '.$a['state'].' '.$a['postalCode'],'fixed_amount'=>['amount'=>$s['shippingCents'],'currency'=>'usd'],'tax_behavior'=>'exclusive']]],
            'metadata'=>['order_id'=>$s['orderId'],'checkout_record'=>(string)$row['id'],'proof_id'=>$s['proofId']],
            'payment_intent_data'=>['metadata'=>['order_id'=>$s['orderId']]],'invoice_creation'=>['enabled'=>'true'],
            'success_url'=>$origin.$basePath.'/shop/?payment=returned&order='.rawurlencode($s['orderId']),
            'cancel_url'=>$origin.$basePath.'/shop/?payment=cancelled&order='.rawurlencode($s['orderId']),
            'custom_text'=>['submit'=>['message'=>'Production: '.$s['productionMinDays'].'–'.$s['productionMaxDays'].' business days after payment and artwork approval. Shipping: '.$s['transitMinDays'].'–'.$s['transitMaxDays'].' business days. Ship to '.$a['line1'].', '.$a['city'].', '.$a['state'].' '.$a['postalCode'].'.']]];
        // The quoted shipping destination stays in the private order. Stripe calculates
        // shipping-address tax from a customer with exactly that saved address.
        $customer=$this->stripe('POST','/customers',['email'=>$s['email'],'name'=>$a['name'],'address'=>['line1'=>$a['line1'],'line2'=>$a['line2'],'city'=>$a['city'],'state'=>$a['state'],'postal_code'=>$a['postalCode'],'country'=>'US'],'shipping'=>['name'=>$a['name'],'address'=>['line1'=>$a['line1'],'line2'=>$a['line2'],'city'=>$a['city'],'state'=>$a['state'],'postal_code'=>$a['postalCode'],'country'=>'US']]],'mled-customer-'.$row['id']);
        unset($params['customer_email']);$params['customer']=$customer['id'];
        $session=$this->stripe('POST','/checkout/sessions',$params,'mled-checkout-'.$row['id']);
        if (!is_string($session['id']??null)||!preg_match('/^cs_(live|test)_[A-Za-z0-9]+$/D',$session['id'])||!is_string($session['url']??null)||parse_url($session['url'],PHP_URL_HOST)!=='checkout.stripe.com'||parse_url($session['url'],PHP_URL_SCHEME)!=='https') throw new PortalError('The payment service did not return a valid checkout.',502);
        $this->exec("UPDATE commerce_checkouts SET provider_id=?,url=?,expires_at=?,state='open' WHERE id=? AND state='creating'",[$session['id'],$session['url'],(int)($session['expires_at']??0),$row['id']]);
        return ['checkoutUrl'=>$session['url'],'orderId'=>$order['id']];
    }
    private function refresh(array $data): array
    {
        $order=$this->order($data['orderId']??null);$row=$this->rows('SELECT * FROM commerce_checkouts WHERE order_id=? ORDER BY id DESC LIMIT 1',[$order['id']])[0]??null;
        if ($row&&$row['provider_id']&&in_array($row['state'],['open','creating'],true)) $this->reconcile($this->stripe('GET','/checkout/sessions/'.rawurlencode($row['provider_id']),['expand'=>['line_items']]));
        return ['commerce'=>self::publicTerms($this->db,$order['id'])];
    }
    public function webhook(): never
    {
        if (!self::available($this->config)) throw new PortalError('Checkout is not configured.',503);
        $raw=(string)file_get_contents('php://input',false,null,0,1048577);if (strlen($raw)>1048576) throw new PortalError('Webhook too large.',413);
        $header=(string)($_SERVER['HTTP_STRIPE_SIGNATURE']??'');$timestamp=null;$signatures=[];
        foreach(explode(',',$header) as $part) { $pair=explode('=',$part,2);if(count($pair)!==2)continue;if($pair[0]==='t'&&preg_match('/^[0-9]{1,12}$/D',$pair[1])===1)$timestamp=(int)$pair[1];if($pair[0]==='v1')$signatures[]=$pair[1]; }
        if ($timestamp===null||abs(time()-$timestamp)>300) throw new PortalError('Invalid payment signature.',400);
        $expected=hash_hmac('sha256',$timestamp.'.'.$raw,$this->config['commerce']['stripe_webhook_secret']);$valid=false;foreach($signatures as $signature) if(hash_equals($expected,$signature))$valid=true;
        if (!$valid) throw new PortalError('Invalid payment signature.',400);
        try {$event=json_decode($raw,true,64,JSON_THROW_ON_ERROR);}catch(Throwable){throw new PortalError('Invalid webhook.',400);}
        if (!is_string($event['id']??null)||!preg_match('/^evt_[A-Za-z0-9]+$/D',$event['id'])) throw new PortalError('Invalid webhook event.',400);
        if ($this->rows('SELECT 1 FROM commerce_webhooks WHERE event_id=?',[$event['id']])) portal_json(['ok'=>true]);
        if (in_array($event['type']??'', ['checkout.session.completed','checkout.session.async_payment_succeeded','checkout.session.expired'],true)) {
            $id=$event['data']['object']['id']??'';if(!is_string($id)||!preg_match('/^cs_(live|test)_[A-Za-z0-9]+$/D',$id))throw new PortalError('Invalid payment session.',400);
            // Retrieve canonical payment data using the merchant key as well as verifying the event.
            $this->reconcile($this->stripe('GET','/checkout/sessions/'.rawurlencode($id),['expand'=>['line_items']]));
        }
        $this->exec('INSERT OR IGNORE INTO commerce_webhooks(event_id,processed_at) VALUES(?,?)',[$event['id'],time()]);portal_json(['ok'=>true]);
    }
    public function reconcile(array $session): void
    {
        $this->db->exec('BEGIN IMMEDIATE');
        try {
            $row=$this->rows('SELECT * FROM commerce_checkouts WHERE provider_id=?',[$session['id']??''])[0]??null;
            if (!$row) { $this->db->exec('COMMIT');return; }
            if ($row['state']==='paid') { $this->db->exec('COMMIT');return; }
            $s=json_decode($row['snapshot'],true,32,JSON_THROW_ON_ERROR);
            $order=$this->rows('SELECT * FROM business_orders WHERE id=?',[$row['order_id']])[0];
            if (($session['payment_status']??'')!=='paid') {
                if (($session['status']??'')==='expired') $this->exec("UPDATE commerce_checkouts SET state='expired' WHERE id=? AND state IN ('creating','open')",[$row['id']]);
                $this->db->exec('COMMIT');return;
            }
            $tax=$session['total_details']['amount_tax']??null;$shipping=$session['total_details']['amount_shipping']??null;$total=$session['amount_total']??null;
            $matches=($session['mode']??'')==='payment'&&($session['currency']??'')==='usd'&&($session['livemode']??null)===($s['mode']==='live')
                &&($session['client_reference_id']??'')===$s['orderId']&&($session['metadata']['order_id']??'')===$s['orderId']&&($session['metadata']['checkout_record']??'')===(string)$row['id']&&($session['metadata']['proof_id']??'')===$s['proofId']
                &&($session['amount_subtotal']??null)===$s['productCents']&&$shipping===$s['shippingCents']&&is_int($tax)&&$tax>=0&&is_int($total)&&$total===$s['productCents']+$s['shippingCents']+$tax
                &&($session['automatic_tax']['status']??'')==='complete'&&($session['total_details']['amount_discount']??0)===0
                &&$order['proof_id']===$s['proofId']&&$order['approved_proof_id']===$s['proofId']&&(int)$order['quote_cents']===$s['productCents']&&$order['status']!=='CANCELLED'
                &&is_string($session['payment_intent']??null)&&preg_match('/^pi_[A-Za-z0-9]+$/D',$session['payment_intent'])===1;
            $items=$session['line_items']['data']??[];
            $matches=$matches&&is_array($items)&&count($items)===1&&($items[0]['quantity']??null)===1&&($items[0]['amount_subtotal']??null)===$s['productCents'];
            if (!$matches) { $this->exec("UPDATE commerce_checkouts SET state='review' WHERE id=?",[$row['id']]);$this->event($order,'PAYMENT_REVIEW','A payment needs review. Contact Mirroried LED before trying to pay again.');$this->db->exec('COMMIT');return; }
            $this->exec("UPDATE commerce_checkouts SET state='paid',payment_intent=?,paid_cents=?,tax_cents=?,paid_at=? WHERE id=?",[$session['payment_intent'],$total,$tax,time(),$row['id']]);
            $this->exec('UPDATE business_orders SET finance_reference=?,updated_at=?,revision=revision+1 WHERE id=?',[$session['payment_intent'],time(),$order['id']]);
            $this->event($order,'PAYMENT_CONFIRMED','Your payment is confirmed. Production is estimated at '.$s['productionMinDays'].'–'.$s['productionMaxDays'].' business days after payment and artwork approval, followed by '.$s['transitMinDays'].'–'.$s['transitMaxDays'].' business days in transit.');
            $this->db->exec('COMMIT');
        } catch(Throwable $e) { try {$this->db->exec('ROLLBACK');}catch(Throwable){}throw $e; }
    }
}
