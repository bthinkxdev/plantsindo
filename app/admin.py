from django.contrib import admin
from .models import Address, Banner, BlogPost, Cart, CartItem, Category, ContactMessage, HomeCategory, HomeCategoryProduct, NewsletterSubscription, Order, OrderItem, Payment, Product, ProductAttribute, ProductAttributeValue, ProductComboItem, ProductContent, ProductFAQ, ProductHighlight, ProductSpecification, ProductWhatsInBoxItem, Reel, Review, Variant, VariantAttributeValue, VariantImage, Wishlist

from django.core.cache import caches

def _invalidate_home_cache():
    try:
        c = caches['locmem']
        for key in [
            'home_product_data_v1',
            'home_shop_categories_v1',
            'home_reels_v1',
            'home_testimonials_v1',
            'home_combos_v1',
        ]:
            c.delete(key)
    except Exception:
        pass
class HomeCategoryProductInline(admin.TabularInline):
    model = HomeCategoryProduct
    extra = 0
    ordering = ('display_order', 'id')
    autocomplete_fields = ('product',)

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('full_path', 'name', 'parent', 'slug', 'is_active')
    list_filter = ('is_active', 'parent')
    list_select_related = ('parent',)
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)
    ordering = ('parent__name', 'name', 'id')
    fieldsets = (
        (None, {'fields': ('name', 'parent', 'slug', 'is_active')}),
        ('Shop & media', {'fields': ('image', 'banner_image', 'banner_tagline')}),
    )

    @admin.display(description='Path')
    def full_path(self, obj: Category):
        try:
            return obj.get_full_path()
        except Exception:
            return obj.name

@admin.register(HomeCategory)
class HomeCategoryAdmin(admin.ModelAdmin):
    list_display = ('display_order', 'name', 'is_active', 'linked_category')
    list_filter = ('is_active',)
    list_select_related = ('linked_category',)
    ordering = ('display_order', 'name', 'id')
    search_fields = ('name', 'slug', 'description')
    prepopulated_fields = {'slug': ('name',)}
    inlines = (HomeCategoryProductInline,)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        _invalidate_home_cache()

class ProductComboItemInline(admin.TabularInline):
    model = ProductComboItem
    fk_name = 'combo_product'
    extra = 0
    autocomplete_fields = ('component_product',)
    ordering = ('display_order', 'id')


class ProductHighlightInline(admin.TabularInline):
    model = ProductHighlight
    extra = 0
    ordering = ('display_order', 'id')


class ProductWhatsInBoxItemInline(admin.TabularInline):
    model = ProductWhatsInBoxItem
    extra = 0
    ordering = ('display_order', 'id')


class ProductSpecificationInline(admin.TabularInline):
    model = ProductSpecification
    extra = 0
    ordering = ('display_order', 'id')


class ProductFAQInline(admin.TabularInline):
    model = ProductFAQ
    extra = 0
    ordering = ('display_order', 'id')


class ProductContentInline(admin.StackedInline):
    model = ProductContent
    max_num = 1
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    # Rental is managed exclusively in the custom dashboard (not Django admin).
    list_display = ('name', 'category', 'purchase_enabled', 'is_combo_product', 'plant_type', 'difficulty', 'beginner_friendly', 'is_plant_combo', 'is_featured', 'is_bestseller', 'is_active')
    list_filter = ('category', 'purchase_enabled', 'is_combo_product', 'plant_type', 'difficulty', 'sunlight', 'watering', 'beginner_friendly', 'air_purifying', 'office_friendly', 'is_plant_combo', 'is_featured', 'is_bestseller', 'is_active')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name', 'brand', 'description')
    readonly_fields = ('average_rating', 'total_reviews')
    inlines = (ProductComboItemInline, ProductHighlightInline, ProductWhatsInBoxItemInline, ProductSpecificationInline, ProductFAQInline, ProductContentInline)

    def get_inline_instances(self, request, obj=None):
        instances = super().get_inline_instances(request, obj)
        if obj is not None and not getattr(obj, 'is_combo_product', False):
            return [i for i in instances if getattr(i, 'model', None) is not ProductComboItem]
        return instances

    fieldsets = (
        (None, {'fields': ('category', 'name', 'slug', 'description', 'brand', 'is_active')}),
        ('Offer types', {'fields': ('purchase_enabled', 'is_combo_product'), 'description': 'Combos: no variants on the parent; add components below.'}),
        ('Simple product (no variants)', {'fields': ('base_price', 'base_original_price', 'base_stock'), 'classes': ('collapse',)}),
        ('Plant & garden', {'fields': ('sunlight', 'watering', 'difficulty', 'plant_type', 'air_purifying', 'beginner_friendly', 'low_maintenance', 'office_friendly', 'is_plant_combo', 'care_instructions')}),
        ('PDP / storefront extras', {'fields': ('video_url', 'germination_time_display', 'harvest_time_display', 'sowing_season_display', 'maintenance_notes', 'is_giftable'), 'classes': ('collapse',)}),
        ('Merchandising', {'fields': ('is_featured', 'is_bestseller', 'is_deal_of_day', 'deal_of_day_start', 'deal_of_day_end')}),
        ('GST', {'fields': ('is_gst_applicable', 'gst_percentage', 'hsn_code'), 'classes': ('collapse',)}),
        ('Ratings (read only)', {'fields': ('average_rating', 'total_reviews'), 'classes': ('collapse',)}),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        _invalidate_home_cache()

class ProductAttributeValueInline(admin.TabularInline):
    model = ProductAttributeValue
    extra = 0
    ordering = ('display_order', 'value')

@admin.register(ProductAttribute)
class ProductAttributeAdmin(admin.ModelAdmin):
    list_display = ('product', 'name', 'display_order')
    list_filter = ('product',)
    inlines = [ProductAttributeValueInline]
    ordering = ('product', 'display_order', 'name')

@admin.register(ProductAttributeValue)
class ProductAttributeValueAdmin(admin.ModelAdmin):
    list_display = ('attribute', 'value', 'display_order')
    list_filter = ('attribute__product',)

class VariantImageInline(admin.TabularInline):
    model = VariantImage
    extra = 0

@admin.register(Variant)
class VariantAdmin(admin.ModelAdmin):
    list_display = ('product', 'price', 'stock_quantity', 'pot_size', 'plant_height_display', 'includes_pot', 'sku', 'is_active', 'display_order')
    list_filter = ('product', 'is_active', 'pot_size', 'includes_pot')
    inlines = [VariantImageInline]
    ordering = ('product', 'display_order', 'id')

    def save_model(self, request, obj, form, change):  
        super().save_model(request, obj, form, change)
        _invalidate_home_cache()

@admin.register(VariantImage)
class VariantImageAdmin(admin.ModelAdmin):
    list_display = ('variant', 'is_primary', 'display_order')

@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'session_key', 'status', 'updated_at')
    list_filter = ('status',)

@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ('cart', 'product', 'selected_variant', 'line_type', 'rental_key', 'is_gift', 'quantity', 'unit_price')
    list_select_related = ('product', 'selected_variant')

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'display_customer', 'display_email', 'display_phone', 'status', 'total', 'payment_status', 'created_at')
    list_filter = ('status',)
    search_fields = ('order_number', 'user__email', 'user__username', 'address__email', 'address__phone', 'address__full_name')
    list_select_related = ('address', 'user')

    def display_customer(self, obj):
        if obj.user_id is None:
            return 'Guest Order'
        return getattr(obj.user, 'email', None) or getattr(obj.user, 'username', str(obj.user))
    display_customer.short_description = 'Customer'

    def display_email(self, obj):
        return obj.address.email or '—' if obj.address_id else '—'
    display_email.short_description = 'Email'

    def display_phone(self, obj):
        return obj.address.phone or '—' if obj.address_id else '—'
    display_phone.short_description = 'Phone'

    def payment_status(self, obj):
        try:
            return obj.payment.get_status_display() if getattr(obj, 'payment', None) else '—'
        except Exception:
            return '—'
    payment_status.short_description = 'Payment'

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'product_name', 'line_type', 'is_gift', 'rental_snapshot', 'variant_snapshot', 'quantity', 'unit_price')
    list_select_related = ('order', 'product', 'selected_variant')

@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'city', 'state', 'is_snapshot')

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('order', 'method', 'status', 'amount', 'processed_at')
    list_select_related = ('order', 'order__address', 'order__user')

@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'subject', 'is_resolved', 'created_at')
    list_filter = ('is_resolved',)

@admin.register(NewsletterSubscription)
class NewsletterSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('email', 'is_active', 'created_at')

@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ('user', 'selected_variant', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__email', 'user__username', 'selected_variant__product__name')
    readonly_fields = ('user', 'selected_variant', 'created_at', 'updated_at')
    ordering = ('-created_at',)
    list_select_related = ('user', 'selected_variant', 'selected_variant__product')

    def has_add_permission(self, request):
        return False

@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'is_published', 'published_at', 'created_at')
    list_filter = ('is_published',)
    search_fields = ('title', 'slug', 'excerpt', 'body')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {'fields': ('title', 'slug', 'excerpt', 'is_published', 'published_at')}),
        ('Content', {'fields': ('body', 'cover_image')}),
        ('Meta', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )


@admin.register(Reel)
class ReelAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_active', 'display_order', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('title', 'caption')
    readonly_fields = ('created_at', 'updated_at')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        _invalidate_home_cache()


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('product', 'user', 'rating', 'is_approved', 'is_deleted', 'created_at')
    list_filter = ('is_approved', 'is_deleted', 'rating')

@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_active', 'display_order', 'created_at')
    list_filter = ('is_active',)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        _invalidate_home_cache()