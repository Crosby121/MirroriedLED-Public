"""Keep the phased opening's public navigation within the approved product scope."""
from html.parser import HTMLParser
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
class Links(HTMLParser):
    def __init__(self): super().__init__(); self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a': self.links.append(dict(attrs).get('href',''))
class OpeningTests(unittest.TestCase):
    def test_home_exposes_only_the_two_products_and_order_account(self):
        text=(ROOT/'index.html').read_text(); parser=Links();parser.feed(text)
        internal={p for p in parser.links if not p.startswith(('#','mailto:'))}
        self.assertEqual(internal,{'./','infinity-builder/','address-builder/','shop/'})
        self.assertIn('finish the full experience',text)
        self.assertIn('Thank you for your patience',text)
    def test_legacy_portal_routes_to_current_customer_orders(self):
        self.assertIn('url=../shop/',(ROOT/'customer-portal/index.html').read_text())
    def test_release_contains_both_builders_checkout_and_internal_access_protection(self):
        import runpy
        files=runpy.run_path(str(ROOT/'deploy/hostinger/package-customer-portal.py'))['PUBLIC_FILES']
        self.assertTrue({'shop/index.html','shop/shop.js','address-builder/index.html','address-builder/builder.js','customer-portal/backend/commerce.php'}<=set(files))
        self.assertIn('commerce\\.php',(ROOT/'customer-portal/backend/.htaccess').read_text())
