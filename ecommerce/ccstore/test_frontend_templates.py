from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from ccstore.models import Category, Product, ProductImage
from payment.models import Order, OrderItem, Payment, RegisterAddress


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class FrontendTemplateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user("frontend", "frontend@example.com", "test-password")
        cls.other = User.objects.create_user("other-frontend", "other@example.com", "test-password")
        cls.category = Category.objects.create(name="Template products", slug="template-products")
        cls.product = Product.objects.create(
            Category=cls.category, title="Template Brush", slug="template-brush",
            sku="TPL-1", price=Decimal("25.00"), image="images/bamboo_brush.jpg",
            stock_quantity=10,
        )
        ProductImage.objects.create(product=cls.product, image="images/pink_brush.jpg")
        cls.out_of_stock = Product.objects.create(
            Category=cls.category, title="Unavailable Brush", slug="unavailable-brush",
            sku="TPL-2", price=Decimal("30.00"), image="images/pink_brush.jpg",
            stock_quantity=0,
        )
        cls.inactive = Product.objects.create(
            Category=cls.category, title="Hidden Brush", slug="hidden-brush", sku="TPL-3",
            price=Decimal("35.00"), image="images/pink_brush.jpg", stock_quantity=10,
            is_active=False,
        )
        cls.address = RegisterAddress.objects.create(
            user=cls.user, label="Home", is_default=True, fullname="Frontend Customer",
            email=cls.user.email, phone="08000000000", address1="1 Template Street",
            city="Lagos", state="Lagos", zipcode="100001", country="Nigeria",
        )
        cls.order = Order.objects.create(
            user=cls.user, fullname="Frontend Customer", email=cls.user.email,
            address1="1 Template Street\nLagos", amount_paid=Decimal("25.00"),
        )
        OrderItem.objects.create(
            order=cls.order, product=cls.product, product_title=cls.product.title,
            product_sku=cls.product.sku, user=cls.user, quantity=1, price=cls.product.price,
        )
        cls.payment = Payment.objects.create(
            order=cls.order, user=cls.user, amount_paid=cls.order.amount_paid,
            email=cls.user.email,
        )

    def assert_single_document(self, response):
        self.assertEqual(response.status_code, 200)
        content = response.content.decode().lower()
        self.assertEqual(content.count("<html"), 1)
        self.assertEqual(content.count("<body"), 1)
        self.assertEqual(content.count("bootstrap@5.3.3/dist/css/bootstrap.min.css"), 1)
        self.assertEqual(content.count("bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"), 1)
        self.assertNotIn("bootstrap@4", content)
        self.assertNotIn("maxcdn.bootstrapcdn.com/bootstrap", content)

    def login(self, user=None):
        self.client.force_login(user or self.user)

    def cart_session(self):
        session = self.client.session
        session["sess_key"] = {str(self.product.id): {"price": str(self.product.price), "product_qty": 1}}
        session.save()

    def test_public_pages_use_one_document_and_shared_navigation(self):
        urls = (
            reverse("store"), self.category.get_absolute_url(), self.product.get_absolute_url(),
            reverse("search") + "?q=Template", reverse("cart_summary"),
        )
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assert_single_document(response)
                self.assertContains(response, reverse("login"))
                self.assertContains(response, reverse("register"))

    def test_product_carousel_has_exactly_one_active_slide(self):
        response = self.client.get(self.product.get_absolute_url())
        self.assertContains(response, 'carousel-item active', count=1)
        self.assertContains(response, self.product.title)

    def test_inactive_detail_is_404_and_out_of_stock_is_labelled(self):
        self.assertEqual(self.client.get(self.inactive.get_absolute_url()).status_code, 404)
        response = self.client.get(self.out_of_stock.get_absolute_url())
        self.assertContains(response, "Out of stock")
        self.assertNotContains(response, "Add to cart")

    def test_search_pagination_preserves_query(self):
        for number in range(13):
            Product.objects.create(
                Category=self.category, title=f"Template extra {number:02d}",
                slug=f"template-extra-{number}", sku=f"TPL-X-{number}", price="1.00",
                image="images/pink_brush.jpg", stock_quantity=1,
            )
        response = self.client.get(reverse("search"), {"q": "Template"})
        self.assertContains(response, "q=Template&amp;page=2")

    def test_authentication_pages_render_with_csrf(self):
        for url in (reverse("register"), reverse("login"), reverse("password_reset"), reverse("resend_verification")):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assert_single_document(response)
                self.assertContains(response, "csrfmiddlewaretoken")
        self.assert_single_document(self.client.get(reverse("email_verification_failed")))

    def test_authenticated_account_pages_render_and_navigation_is_secure(self):
        self.login()
        for url in (reverse("dashboard"), reverse("profile_account"), reverse("manage_shipping_address"), reverse("order_history"), reverse("order_detail", args=(self.order.id,))):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assert_single_document(response)
                self.assertContains(response, reverse("logout"))
        self.assertContains(self.client.get(reverse("profile_account")), "current-password")

    def test_order_detail_is_owner_scoped(self):
        self.login(self.other)
        self.assertEqual(self.client.get(reverse("order_detail", args=(self.order.id,))).status_code, 404)

    def test_empty_and_populated_cart_render_safely(self):
        empty = self.client.get(reverse("cart_summary"))
        self.assertContains(empty, "Your cart is empty")
        self.assertNotContains(empty, "Continue to checkout")
        self.cart_session()
        populated = self.client.get(reverse("cart_summary"))
        self.assertContains(populated, self.product.title)
        self.assertContains(populated, "csrfmiddlewaretoken")
        self.assertContains(populated, "Continue to checkout")

    def test_checkout_renders_server_lines_and_idempotency_token(self):
        self.login()
        self.cart_session()
        response = self.client.get(reverse("checkout"))
        self.assert_single_document(response)
        self.assertContains(response, self.product.title)
        self.assertContains(response, 'name="checkout_token"', html=False)
        self.assertContains(response, "csrfmiddlewaretoken")

    def test_payment_pages_are_exact_owner_scoped_and_read_only(self):
        self.login()
        before = Payment.objects.count()
        make = self.client.get(reverse("makepayment", args=(self.payment.ref,)))
        self.assert_single_document(make)
        self.assertContains(make, self.payment.ref)
        self.assertContains(make, "csrfmiddlewaretoken")
        pending = self.client.get(reverse("payment_pending", args=(self.payment.ref,)))
        self.assert_single_document(pending)
        self.payment.status = Payment.Status.FAILED
        self.payment.save(update_fields=("status", "updated_at"))
        self.order.status = Order.Status.PAYMENT_FAILED
        self.order.save(update_fields=("status", "updated_at"))
        self.assert_single_document(self.client.get(reverse("payment_failed", args=(self.payment.ref,))))
        self.assertEqual(Payment.objects.count(), before)
        self.login(self.other)
        self.assertEqual(self.client.get(reverse("makepayment", args=(self.payment.ref,))).status_code, 302)

    def test_success_page_shows_exact_order_and_stock_issue_language(self):
        self.login()
        self.payment.status = Payment.Status.VERIFIED
        self.payment.save(update_fields=("status", "updated_at"))
        self.order.status = Order.Status.PAID_STOCK_ISSUE
        self.order.save(update_fields=("status", "updated_at"))
        response = self.client.get(reverse("payment_success", args=(self.payment.ref,)))
        self.assert_single_document(response)
        self.assertContains(response, f"order #{self.order.id}", html=False)
        self.assertContains(response, "Staff review required")
        self.assertNotContains(response, "stock was allocated")

    def test_homepage_has_deliberate_sections_and_hides_inactive_products(self):
        response = self.client.get(reverse("store"))
        self.assertContains(response, 'class="hero"', html=False)
        self.assertContains(response, "Shop by collection")
        self.assertContains(response, "Recently added")
        self.assertContains(response, self.product.title)
        self.assertNotContains(response, self.inactive.title)

    def test_product_cards_show_stock_states_and_valid_fallback(self):
        low_stock = Product.objects.create(
            Category=self.category, title="Last Brush", slug="last-brush", sku="TPL-LOW",
            price="12.00", image="", stock_quantity=1, low_stock_threshold=2,
        )
        response = self.client.get(self.category.get_absolute_url())
        self.assertContains(response, "Low stock")
        self.assertContains(response, "Out of stock")
        self.assertContains(response, "media/images/ccbeauty_logo.jpg")
        self.assertContains(response, low_stock.get_absolute_url(), count=2)

    def test_related_products_exclude_current_and_inactive(self):
        related = Product.objects.create(
            Category=self.category, title="Related Brush", slug="related-brush",
            sku="TPL-RELATED", price="15.00", image="images/pink_brush.jpg", stock_quantity=2,
        )
        response = self.client.get(self.product.get_absolute_url())
        related_section = response.content.decode().split("Related products", 1)[1]
        self.assertIn(related.title, related_section)
        self.assertNotIn(self.product.title, related_section)
        self.assertNotIn(self.inactive.title, related_section)

    def test_sorting_is_validated_and_pagination_keeps_selected_sort(self):
        for number in range(13):
            Product.objects.create(
                Category=self.category, title=f"Sorted {number:02d}",
                slug=f"sorted-{number}", sku=f"SORT-{number}", price=number + 1,
                image="images/pink_brush.jpg", stock_quantity=1,
            )
        response = self.client.get(reverse("search"), {"q": "Sorted", "sort": "price_desc"})
        self.assertEqual(response.context["selected_sort"], "price_desc")
        self.assertContains(response, "page=2&amp;sort=price_desc")
        invalid = self.client.get(self.category.get_absolute_url(), {"sort": "__unsafe"})
        self.assertEqual(invalid.context["selected_sort"], "name")

    def test_private_and_search_pages_include_robots_metadata(self):
        self.login()
        for url in (reverse("dashboard"), reverse("checkout"), reverse("order_history")):
            if url == reverse("checkout"):
                self.cart_session()
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), 'content="noindex,nofollow"', html=False)
        self.assertContains(
            self.client.get(reverse("search"), {"q": "Template"}),
            'content="noindex,follow"', html=False,
        )
