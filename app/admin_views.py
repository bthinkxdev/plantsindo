import json
import logging
import time
from datetime import timedelta
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.decorators import user_passes_test
from django.db import connection, transaction, IntegrityError
from django.db.models import Count, Max, Sum, Q, F, ProtectedError, Value
from django.db.models.functions import TruncDate, Coalesce
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView, View
from .models import Banner, BlogPost, CartItem, Category, Combo, ComboItem, ContactMessage, Coupon, CouponRedemption, HomeCategory, Order, OrderItem, Product, ProductAttributeValue, Reel, Review, Shipment, Variant, VariantImage, Testimonial
from django.conf import settings
from app.admin_forms import AdminLoginForm, BannerForm, BlogPostForm, CategoryForm, ComboForm, CouponForm, HomeCategoryForm, ProductBasicEditForm, ReelForm, RentalConfigForm, _validate_image_file, TestimonialForm
from .utils.debug_trace import Trace
from .admin_product_edit_views import ProductCreateBasicView as BaseProductCreateBasicView, ProductEditView as BaseProductEditView, ProductUpdateBasicView as BaseProductUpdateBasicView, ProductToggleActiveView as BaseProductToggleActiveView, ProductAttributesListApiView as BaseProductAttributesListApiView, ProductAttributeCreateApiView as BaseProductAttributeCreateApiView, ProductAttributesReorderApiView as BaseProductAttributesReorderApiView, ProductAttributeUpdateApiView as BaseProductAttributeUpdateApiView, ProductAttributeDeleteApiView as BaseProductAttributeDeleteApiView, ProductAttributeValueCreateApiView as BaseProductAttributeValueCreateApiView, ProductAttributeValuesReorderApiView as BaseProductAttributeValuesReorderApiView, ProductAttributeValueUpdateApiView as BaseProductAttributeValueUpdateApiView, ProductAttributeValueDeleteApiView as BaseProductAttributeValueDeleteApiView, ProductVariantsListApiView as BaseProductVariantsListApiView, VariantCreateApiView as BaseVariantCreateApiView, VariantUpdateApiView as BaseVariantUpdateApiView, VariantDeleteApiView as BaseVariantDeleteApiView, VariantUploadImageView as BaseVariantUploadImageView, VariantImageDeleteView as BaseVariantImageDeleteView, VariantImageSetPrimaryView as BaseVariantImageSetPrimaryView, VariantImageReorderView as BaseVariantImageReorderView, ProductImageUploadView as BaseProductImageUploadView, ProductImageDeleteView as BaseProductImageDeleteView, ProductImageSetPrimaryView as BaseProductImageSetPrimaryView, ProductImageReorderView as BaseProductImageReorderView, ProductComboComponentsListApiView as BaseProductComboComponentsListApiView, ProductComboCandidateProductsApiView as BaseProductComboCandidateProductsApiView, ProductComboComponentAddApiView as BaseProductComboComponentAddApiView, ProductComboComponentUpdateApiView as BaseProductComboComponentUpdateApiView, ProductComboComponentDeleteApiView as BaseProductComboComponentDeleteApiView
logger = logging.getLogger(__name__)
from .services.shiprocket_service import shiprocket_service, ShiprocketAPIError, create_shipment_for_order
from .services import send_order_confirmation_email_async
from .delivery_utils import delivery_enabled

class StaffRequiredMixin(UserPassesTestMixin):

    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_staff

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect('admin_panel:login')
        messages.error(self.request, "You don't have permission to access this area.")
        return redirect('store:home')

class ProductCreateBasicView(StaffRequiredMixin, BaseProductCreateBasicView):
    pass

class ProductEditView(StaffRequiredMixin, BaseProductEditView):
    pass

class ProductUpdateBasicView(StaffRequiredMixin, BaseProductUpdateBasicView):
    pass

class ProductToggleActiveView(StaffRequiredMixin, BaseProductToggleActiveView):
    pass

class ProductAttributesListApiView(StaffRequiredMixin, BaseProductAttributesListApiView):
    pass

class ProductAttributeCreateApiView(StaffRequiredMixin, BaseProductAttributeCreateApiView):
    pass

class ProductAttributesReorderApiView(StaffRequiredMixin, BaseProductAttributesReorderApiView):
    pass

class ProductAttributeUpdateApiView(StaffRequiredMixin, BaseProductAttributeUpdateApiView):
    pass

class ProductAttributeDeleteApiView(StaffRequiredMixin, BaseProductAttributeDeleteApiView):
    pass

class ProductAttributeValueCreateApiView(StaffRequiredMixin, BaseProductAttributeValueCreateApiView):
    pass

class ProductAttributeValuesReorderApiView(StaffRequiredMixin, BaseProductAttributeValuesReorderApiView):
    pass

class ProductAttributeValueUpdateApiView(StaffRequiredMixin, BaseProductAttributeValueUpdateApiView):
    pass

class ProductAttributeValueDeleteApiView(StaffRequiredMixin, BaseProductAttributeValueDeleteApiView):
    pass

class ProductVariantsListApiView(StaffRequiredMixin, BaseProductVariantsListApiView):
    pass

class VariantCreateApiView(StaffRequiredMixin, BaseVariantCreateApiView):
    pass

class VariantUpdateApiView(StaffRequiredMixin, BaseVariantUpdateApiView):
    pass

class VariantDeleteApiView(StaffRequiredMixin, BaseVariantDeleteApiView):
    pass

class VariantUploadImageView(StaffRequiredMixin, BaseVariantUploadImageView):
    pass

class VariantImageDeleteView(StaffRequiredMixin, BaseVariantImageDeleteView):
    pass

class VariantImageSetPrimaryView(StaffRequiredMixin, BaseVariantImageSetPrimaryView):
    pass

class VariantImageReorderView(StaffRequiredMixin, BaseVariantImageReorderView):
    pass

class ProductImageUploadView(StaffRequiredMixin, BaseProductImageUploadView):
    pass

class ProductImageDeleteView(StaffRequiredMixin, BaseProductImageDeleteView):
    pass

class ProductImageSetPrimaryView(StaffRequiredMixin, BaseProductImageSetPrimaryView):
    pass

class ProductImageReorderView(StaffRequiredMixin, BaseProductImageReorderView):
    pass


class ProductComboComponentsListApiView(StaffRequiredMixin, BaseProductComboComponentsListApiView):
    pass


class ProductComboCandidateProductsApiView(StaffRequiredMixin, BaseProductComboCandidateProductsApiView):
    pass


class ProductComboComponentAddApiView(StaffRequiredMixin, BaseProductComboComponentAddApiView):
    pass


class ProductComboComponentUpdateApiView(StaffRequiredMixin, BaseProductComboComponentUpdateApiView):
    pass


class ProductComboComponentDeleteApiView(StaffRequiredMixin, BaseProductComboComponentDeleteApiView):
    pass


class ProductRentalConfigUpdateView(StaffRequiredMixin, View):

    def post(self, request, pk):
        from .models import RentalConfig
        product = get_object_or_404(Product, pk=pk)
        cfg = RentalConfig.objects.filter(product=product).first() or RentalConfig(product=product)
        form = RentalConfigForm(request.POST, instance=cfg)
        if not form.is_valid():
            for field, errs in form.errors.items():
                for e in errs:
                    messages.error(request, f'{field}: {e}')
            return redirect('admin_panel:product_edit', pk=product.pk)
        cfg = form.save()
        # If rental is enabled at config level, ensure storefront flag is ON.
        if cfg.is_rent_enabled and not product.is_rent_available:
            Product.objects.filter(pk=product.pk).update(is_rent_available=True)
        messages.success(request, 'Rental configuration saved.')
        return redirect('admin_panel:product_edit', pk=product.pk)


class DashboardRentalListView(StaffRequiredMixin, TemplateView):
    template_name = 'dashboard/rentals/list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = (
            Product.objects.filter(is_rent_available=True)
            .select_related('category')
            .select_related('rental_config')
            .order_by('-created_at')
        )
        context['active_menu'] = 'rentals'
        context['products'] = list(qs[:500])
        return context


class DashboardRentalBookingsView(StaffRequiredMixin, TemplateView):
    template_name = 'dashboard/rentals/bookings.html'

    def get_context_data(self, **kwargs):
        from .models import RentalBooking
        context = super().get_context_data(**kwargs)
        status = (self.request.GET.get('status') or '').strip().lower()
        qs = RentalBooking.objects.select_related('product', 'user', 'order_item', 'order_item__order').order_by('-created_at')
        if status in dict(RentalBooking.Status.choices):
            qs = qs.filter(status=status)
        context['active_menu'] = 'rentals'
        context['bookings'] = list(qs[:500])
        context['filter_status'] = status
        context['status_choices'] = RentalBooking.Status.choices
        return context


class DashboardRentalBookingStatusUpdateView(StaffRequiredMixin, View):

    def post(self, request, booking_id):
        from .models import RentalBooking
        booking = get_object_or_404(RentalBooking, pk=booking_id)
        new_status = (request.POST.get('status') or '').strip()
        if new_status not in dict(RentalBooking.Status.choices):
            messages.error(request, 'Invalid status.')
            return redirect('admin_panel:rental_bookings')
        booking.status = new_status
        booking.save(update_fields=['status', 'updated_at'])
        messages.success(request, 'Booking status updated.')
        return redirect('admin_panel:rental_bookings')

class AdminLoginView(View):
    template_name = 'admin_panel/login.html'

    def get(self, request):
        if request.user.is_authenticated and request.user.is_staff:
            return redirect('admin_panel:dashboard')
        form = AdminLoginForm()
        return render(request, self.template_name, {'form': form, 'captcha_site_key': settings.CAPTCHA_SITE_KEY})

    def post(self, request):
        form = AdminLoginForm(request.POST)
        if form.is_valid():
            from app.captcha import CaptchaError, captcha_required, extract_captcha_token, verify_captcha
            from app.views import get_client_ip
            try:
                if captcha_required():
                    verify_captcha(extract_captcha_token(request), remote_ip=get_client_ip(request))
            except CaptchaError as exc:
                messages.error(request, str(exc))
                return render(request, self.template_name, {'form': form, 'captcha_site_key': settings.CAPTCHA_SITE_KEY})
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)
            if user and user.is_staff:
                login(request, user)
                messages.success(request, f'Welcome back, {user.username}!')
                return redirect('admin_panel:dashboard')
            else:
                messages.error(request, 'Invalid credentials or insufficient permissions.')
        return render(request, self.template_name, {'form': form, 'captcha_site_key': settings.CAPTCHA_SITE_KEY})

class AdminLogoutView(View):

    def post(self, request):
        logout(request)
        messages.success(request, 'Logged out successfully.')
        return redirect('admin_panel:login')

class AdminDashboardView(StaffRequiredMixin, TemplateView):
    template_name = 'admin/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        last_7_days = today - timedelta(days=7)
        last_30_days = today - timedelta(days=30)
        total_orders = Order.objects.count()
        orders_today = Order.objects.filter(created_at__date=today).count()
        orders_this_week = Order.objects.filter(created_at__date__gte=last_7_days).count()
        orders_this_month = Order.objects.filter(created_at__date__gte=last_30_days).count()
        total_revenue = Order.objects.aggregate(total=Sum('total'))['total'] or 0
        revenue_today = Order.objects.filter(created_at__date=today).aggregate(total=Sum('total'))['total'] or 0
        revenue_this_week = Order.objects.filter(created_at__date__gte=last_7_days).aggregate(total=Sum('total'))['total'] or 0
        revenue_this_month = Order.objects.filter(created_at__date__gte=last_30_days).aggregate(total=Sum('total'))['total'] or 0
        order_status = Order.objects.values('status').annotate(count=Count('id'))
        total_products = Product.objects.filter(is_active=True).count()
        _low = getattr(settings, 'LOW_STOCK_THRESHOLD', 5)
        low_stock_variants = Variant.objects.filter(
            is_active=True, stock_quantity__gt=0, stock_quantity__lte=_low
        ).count()
        low_stock_simple = Product.objects.filter(is_active=True).annotate(
            _vc=Count('variants')
        ).filter(_vc=0, base_stock__gt=0, base_stock__lte=_low).count()
        low_stock_products = low_stock_variants + low_stock_simple
        out_of_stock_products = Variant.objects.filter(is_active=True, stock_quantity=0).count()
        recent_orders = Order.objects.select_related('address').order_by('-created_at')[:10]
        top_rows = list(OrderItem.objects.filter(order__created_at__gte=last_30_days).exclude(order__status=Order.Status.CANCELLED).values('product_id').annotate(total_sold=Sum('quantity'), revenue=Sum(F('quantity') * F('unit_price'))).order_by('-total_sold')[:5])
        if top_rows:
            product_ids = [r['product_id'] for r in top_rows]
            products_by_id = {p.pk: p for p in Product.objects.filter(pk__in=product_ids)}
            top_products = []
            for r in top_rows:
                p = products_by_id.get(r['product_id'])
                if p:
                    top_products.append(type('TopProductRow', (), {'name': p.name, 'total_sold': r['total_sold'], 'revenue': r['revenue'] or 0})())
        else:
            top_products = []
        unresolved_messages = ContactMessage.objects.filter(is_resolved=False).count()
        import json
        chart_data = []
        for i in range(13, -1, -1):
            date = today - timedelta(days=i)
            daily_revenue = Order.objects.filter(created_at__date=date).aggregate(total=Sum('total'))['total'] or 0
            chart_data.append({'date': date.strftime('%d %b'), 'revenue': float(daily_revenue)})
        chart_data_json = json.dumps(chart_data)
        context.update({'total_orders': total_orders, 'orders_today': orders_today, 'orders_this_week': orders_this_week, 'orders_this_month': orders_this_month, 'total_revenue': total_revenue, 'revenue_today': revenue_today, 'revenue_this_week': revenue_this_week, 'revenue_this_month': revenue_this_month, 'order_status': order_status, 'total_products': total_products, 'low_stock_products': low_stock_products, 'out_of_stock_products': out_of_stock_products, 'recent_orders': recent_orders, 'top_products': top_products, 'unresolved_messages': unresolved_messages, 'chart_data': chart_data_json, 'active_menu': 'dashboard'})
        return context

class CategoryListView(StaffRequiredMixin, ListView):
    model = Category
    template_name = 'admin/category_list.html'
    context_object_name = 'categories'
    paginate_by = 20

    def get_queryset(self):
        qs = Category.objects.select_related('parent').annotate(product_count=Count('products'))
        search = self.request.GET.get('search')
        parent = self.request.GET.get('parent')
        if search:
            qs = qs.filter(Q(name__icontains=search))
        if parent:
            if parent == 'root':
                qs = qs.filter(parent__isnull=True)
            else:
                try:
                    qs = qs.filter(parent_id=int(parent))
                except (TypeError, ValueError):
                    pass
        return qs.order_by('parent__name', 'name', '-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'categories'
        context['search_query'] = self.request.GET.get('search', '')
        context['parent_filter'] = self.request.GET.get('parent', '')
        context['parent_categories'] = list(Category.objects.filter(parent__isnull=True).order_by('name').only('id', 'name'))
        return context

class CategoryCreateView(StaffRequiredMixin, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = 'admin/category_form.html'
    success_url = reverse_lazy('admin_panel:category_list')

    def form_valid(self, form):
        messages.success(self.request, 'Category created successfully!')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'categories'
        context['form_title'] = 'Create Category'
        return context

class CategoryUpdateView(StaffRequiredMixin, UpdateView):
    model = Category
    form_class = CategoryForm
    template_name = 'admin/category_form.html'
    success_url = reverse_lazy('admin_panel:category_list')

    def form_valid(self, form):
        messages.success(self.request, 'Category updated successfully!')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'categories'
        context['form_title'] = 'Edit Category'
        return context

class CategoryDeleteView(StaffRequiredMixin, DeleteView):
    model = Category
    success_url = reverse_lazy('admin_panel:category_list')

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.products.exists():
            messages.error(request, 'Cannot delete category with existing products.')
            return redirect('admin_panel:category_list')
        success_url = self.get_success_url()
        category_name = self.object.name
        if self.object.image:
            try:
                image_name = self.object.image.name
                storage = self.object.image.storage
                Category.objects.filter(pk=self.object.pk).update(image=None)
                try:
                    storage.delete(image_name)
                except Exception:
                    pass
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f'Failed to delete category image: {str(e)}')
        try:
            Category.objects.filter(pk=self.object.pk).delete()
            messages.success(request, f"Category '{category_name}' deleted successfully!")
        except Exception as e:
            messages.error(request, f'Error deleting category: {str(e)}')
        return redirect(success_url)

class BannerListView(StaffRequiredMixin, ListView):
    model = Banner
    template_name = 'admin/banner_list.html'
    context_object_name = 'banners'
    paginate_by = 20

    def get_queryset(self):
        qs = Banner.objects.all()
        status = self.request.GET.get('status')
        if status == 'active':
            qs = qs.filter(is_active=True)
        elif status == 'inactive':
            qs = qs.filter(is_active=False)
        return qs.order_by('display_order', 'created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'banners'
        context['filter_status'] = self.request.GET.get('status', '')
        context['max_active'] = Banner.MAX_ACTIVE
        return context

class BannerCreateView(StaffRequiredMixin, CreateView):
    model = Banner
    form_class = BannerForm
    template_name = 'admin/banner_form.html'
    success_url = reverse_lazy('admin_panel:banner_list')

    def form_valid(self, form):
        messages.success(self.request, 'Banner created successfully!')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'banners'
        context['form_title'] = 'Create Banner'
        context['max_active'] = Banner.MAX_ACTIVE
        return context

class BannerUpdateView(StaffRequiredMixin, UpdateView):
    model = Banner
    form_class = BannerForm
    template_name = 'admin/banner_form.html'
    success_url = reverse_lazy('admin_panel:banner_list')

    def form_valid(self, form):
        messages.success(self.request, 'Banner updated successfully!')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'banners'
        context['form_title'] = 'Edit Banner'
        context['max_active'] = Banner.MAX_ACTIVE
        return context

class BannerDeleteView(StaffRequiredMixin, DeleteView):
    model = Banner
    success_url = reverse_lazy('admin_panel:banner_list')

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        success_url = self.get_success_url()
        if self.object.image:
            try:
                image_name = self.object.image.name
                storage = self.object.image.storage
                Banner.objects.filter(pk=self.object.pk).update(image=None)
                try:
                    storage.delete(image_name)
                except Exception:
                    pass
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f'Failed to delete banner image: {str(e)}')
        try:
            Banner.objects.filter(pk=self.object.pk).delete()
            messages.success(request, 'Banner deleted successfully!')
        except Exception as e:
            messages.error(request, f'Error deleting banner: {str(e)}')
        return redirect(success_url)

class ProductListView(StaffRequiredMixin, ListView):
    model = Product
    template_name = 'admin/product_list.html'
    context_object_name = 'products'
    paginate_by = 20

    def get_queryset(self):
        qs = Product.objects.select_related('category').prefetch_related('variants')
        search = self.request.GET.get('search')
        category = self.request.GET.get('category')
        status = self.request.GET.get('status')
        offer = self.request.GET.get('offer')
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search))
        if category:
            qs = qs.filter(category_id=category)
        if status == 'active':
            qs = qs.filter(is_active=True)
        elif status == 'inactive':
            qs = qs.filter(is_active=False)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'products'
        context['categories'] = Category.objects.filter(is_active=True).select_related('parent').order_by('parent__name', 'name')
        context['search_query'] = self.request.GET.get('search', '')
        context['filter_category'] = self.request.GET.get('category', '')
        context['filter_status'] = self.request.GET.get('status', '')
        _low = getattr(settings, 'LOW_STOCK_THRESHOLD', 5)
        for product in context['products']:
            product.inventory_count = product.get_stock()
            product.display_price = product.get_price()
            stock = product.inventory_count
            product.is_low_stock = 0 < stock <= _low
            product.is_out_of_stock = stock == 0
        return context


class DashboardComboListView(StaffRequiredMixin, ListView):
    model = Combo
    template_name = 'dashboard/combos/list.html'
    context_object_name = 'combos'
    paginate_by = 30

    def get_queryset(self):
        return Combo.objects.annotate(combo_line_count=Count('items')).order_by('-updated_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'combos'
        return context


class DashboardComboCreateView(StaffRequiredMixin, CreateView):
    model = Combo
    form_class = ComboForm
    template_name = 'dashboard/combos/form.html'

    def form_valid(self, form):
        messages.success(self.request, 'Combo created. Add products to the bundle below.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('admin_panel:combo_edit', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'combos'
        context['form_title'] = 'New combo bundle'
        context['editing'] = False
        return context


class DashboardComboUpdateView(StaffRequiredMixin, UpdateView):
    model = Combo
    form_class = ComboForm
    template_name = 'dashboard/combos/form.html'

    def form_valid(self, form):
        messages.success(self.request, 'Combo updated.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('admin_panel:combo_edit', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'combos'
        context['form_title'] = f'Edit: {self.object.name}'
        context['editing'] = True
        return context


class ComboBundleItemsListApiView(StaffRequiredMixin, View):

    def get(self, request, pk):
        combo = get_object_or_404(Combo, pk=pk)
        rows = combo.items.select_related('product').order_by('display_order', 'id')
        return JsonResponse(
            {
                'components': [
                    {
                        'id': r.id,
                        'component_product_id': r.product_id,
                        'name': r.product.name,
                        'quantity': r.quantity,
                        'display_order': r.display_order,
                    }
                    for r in rows
                ]
            }
        )


class ComboBundleCandidatesApiView(StaffRequiredMixin, View):

    def get(self, request, pk):
        combo = get_object_or_404(Combo, pk=pk)
        q = (request.GET.get('q') or '').strip()
        in_combo = set(combo.items.values_list('product_id', flat=True))
        qs = (
            Product.objects.filter(is_active=True, is_combo_product=False)
            .annotate(vc=Count('variants'))
            .filter(vc=0)
            .exclude(pk__in=in_combo)
        )
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(slug__icontains=q))
        qs = qs.order_by('name')[:40]
        return JsonResponse({'products': [{'id': p.id, 'name': p.name} for p in qs]})


class ComboBundleItemAddApiView(StaffRequiredMixin, View):

    def post(self, request, pk):
        combo = get_object_or_404(Combo, pk=pk)
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'errors': {'__all__': ['Invalid JSON']}}, status=400)
        try:
            cid = int(data.get('component_product_id'))
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'errors': {'component_product_id': ['Invalid product.']}}, status=400)
        try:
            qty = int(data.get('quantity', 1))
        except (TypeError, ValueError):
            qty = 1
        qty = max(1, qty)
        child = (
            Product.objects.filter(pk=cid)
            .annotate(vc=Count('variants'))
            .filter(vc=0)
            .exclude(is_combo_product=True)
            .exclude(pk__in=combo.items.values_list('product_id', flat=True))
            .first()
        )
        if not child:
            return JsonResponse({'success': False, 'errors': {'component_product_id': ['Choose an active simple product not already in this bundle.']}}, status=400)
        next_order = (combo.items.aggregate(m=Max('display_order')).get('m') or -1) + 1
        try:
            row = ComboItem.objects.create(combo=combo, product=child, quantity=qty, display_order=next_order)
        except IntegrityError:
            return JsonResponse({'success': False, 'errors': {'__all__': ['This product is already in the bundle.']}}, status=400)
        combo.refresh_from_db()
        from app.services.combo_catalog import assert_combo_valid
        from django.core.exceptions import ValidationError as DjangoValidationError

        try:
            assert_combo_valid(combo)
        except DjangoValidationError as exc:
            row.delete()
            msg = exc.messages[0] if hasattr(exc, 'messages') and exc.messages else str(exc)
            return JsonResponse({'success': False, 'errors': {'__all__': [msg]}}, status=400)
        return JsonResponse(
            {
                'success': True,
                'component': {
                    'id': row.id,
                    'component_product_id': row.product_id,
                    'name': child.name,
                    'quantity': row.quantity,
                    'display_order': row.display_order,
                },
            }
        )


class ComboBundleItemUpdateApiView(StaffRequiredMixin, View):

    def post(self, request, row_id):
        row = get_object_or_404(ComboItem, pk=row_id)
        combo = row.combo
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'errors': {'__all__': ['Invalid JSON']}}, status=400)
        update_kw = {}
        if 'quantity' in data:
            try:
                q = int(data['quantity'])
                update_kw['quantity'] = max(1, q)
            except (TypeError, ValueError):
                return JsonResponse({'success': False, 'errors': {'quantity': ['Invalid quantity.']}}, status=400)
        if 'display_order' in data:
            try:
                update_kw['display_order'] = max(0, int(data['display_order']))
            except (TypeError, ValueError):
                return JsonResponse({'success': False, 'errors': {'display_order': ['Invalid order.']}}, status=400)
        if update_kw:
            ComboItem.objects.filter(pk=row.pk).update(**update_kw)
        row.refresh_from_db()
        from app.services.combo_catalog import assert_combo_valid
        from django.core.exceptions import ValidationError as DjangoValidationError

        try:
            assert_combo_valid(combo)
        except DjangoValidationError as exc:
            msg = exc.messages[0] if hasattr(exc, 'messages') and exc.messages else str(exc)
            return JsonResponse({'success': False, 'errors': {'__all__': [msg]}}, status=400)
        return JsonResponse(
            {
                'success': True,
                'component': {
                    'id': row.id,
                    'component_product_id': row.product_id,
                    'name': row.product.name,
                    'quantity': row.quantity,
                    'display_order': row.display_order,
                },
            }
        )


class ComboBundleItemDeleteApiView(StaffRequiredMixin, View):

    def post(self, request, row_id):
        row = get_object_or_404(ComboItem, pk=row_id)
        row.delete()
        return JsonResponse({'success': True})


class HomeCategoryListView(StaffRequiredMixin, ListView):
    model = HomeCategory
    template_name = 'admin/home_category_list.html'
    context_object_name = 'home_categories'
    paginate_by = 50

    def get_queryset(self):
        return HomeCategory.objects.select_related('linked_category').order_by('display_order', 'name', 'id')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'home_categories'
        return context


class HomeCategoryCreateView(StaffRequiredMixin, CreateView):
    model = HomeCategory
    form_class = HomeCategoryForm
    template_name = 'admin/home_category_form.html'
    success_url = reverse_lazy('admin_panel:home_category_list')

    def form_valid(self, form):
        messages.success(self.request, 'Home category added.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'home_categories'
        context['form_title'] = 'Add Home Category'
        return context


class HomeCategoryUpdateView(StaffRequiredMixin, UpdateView):
    model = HomeCategory
    form_class = HomeCategoryForm
    template_name = 'admin/home_category_form.html'
    success_url = reverse_lazy('admin_panel:home_category_list')

    def form_valid(self, form):
        messages.success(self.request, 'Home category updated.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'home_categories'
        context['form_title'] = 'Edit Home Category'
        return context


class HomeCategoryDeleteView(StaffRequiredMixin, DeleteView):
    model = HomeCategory
    success_url = reverse_lazy('admin_panel:home_category_list')

    def post(self, request, *args, **kwargs):
        obj = self.get_object()
        name = obj.name
        obj.delete()
        messages.success(request, f'Removed "{name}" from home categories.')
        return redirect(self.success_url)

class ProductCreateView(StaffRequiredMixin, TemplateView):
    template_name = 'admin/product_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'products'
        context['form_title'] = 'Add Product'
        context['basic_form'] = ProductBasicEditForm(instance=None)
        return context

class ProductDeleteView(StaffRequiredMixin, DeleteView):
    model = Product
    success_url = reverse_lazy('admin_panel:product_list')

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        product_name = self.object.name
        success_url = self.get_success_url()
        
        from app.models.combo import ComboItem
        combo_items = ComboItem.objects.filter(product=self.object).select_related('combo')
        if combo_items.exists():
            combo_names = ", ".join([ci.combo.name for ci in combo_items])
            messages.error(request, f'Cannot delete product "{product_name}". It is included in the following Combo Bundle(s): {combo_names}.')
            return redirect(success_url)
            
        if OrderItem.objects.filter(product=self.object).exists():
            messages.error(request, f'Cannot delete product "{product_name}". It is linked to existing orders.')
            return redirect(success_url)
        CartItem.objects.filter(product=self.object).delete()
        for variant in self.object.variants.all():
            for img in variant.images.all():
                if img.image:
                    try:
                        image_name = img.image.name
                        storage = img.image.storage
                        VariantImage.objects.filter(pk=img.pk).update(image=None)
                        try:
                            storage.delete(image_name)
                        except Exception:
                            pass
                    except Exception as e:
                        logger.warning('Failed to delete variant image: %s', str(e))
        try:
            self.object.delete()
            messages.success(request, f'Product "{product_name}" has been deleted successfully.')
        except ProtectedError as e:
            messages.error(request, f'Cannot delete product "{product_name}". It is protected by existing order data.')
        except Exception as e:
            messages.error(request, f'Could not delete product: {str(e)}')
        return redirect(success_url)

class ProductDeleteCheckView(StaffRequiredMixin, View):

    def get(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        
        # Check if included in combos
        from app.models.combo import ComboItem
        combo_items = ComboItem.objects.filter(product=product).select_related('combo')
        if combo_items.exists():
            combo_names = ", ".join([ci.combo.name for ci in combo_items])
            return JsonResponse({
                'can_delete': False, 
                'has_active_orders': False, 
                'has_orders': False, 
                'message': f'Cannot delete "{product.name}". It is included in the following Combo Bundle(s): {combo_names}'
            })
            
        all_orders = Order.objects.filter(items__product=product).distinct()
        active_orders = all_orders.exclude(status__in=['delivered', 'cancelled']).distinct()
        if active_orders.exists():
            return JsonResponse({'can_delete': False, 'has_active_orders': True, 'has_orders': True, 'message': f'Cannot delete: {active_orders.count()} active order(s)'})
        if not all_orders.exists():
            return JsonResponse({'can_delete': True, 'will_delete_completely': True, 'has_orders': False, 'message': 'Product will be completely deleted'})
        return JsonResponse({'can_delete': True, 'will_delete_completely': False, 'has_orders': True, 'message': 'Product will be set to inactive'})

class OrderListView(StaffRequiredMixin, ListView):
    model = Order
    template_name = 'admin/order_list.html'
    context_object_name = 'orders'
    paginate_by = 20

    def get_queryset(self):
        qs = Order.objects.select_related('address').prefetch_related('items')
        search = self.request.GET.get('search')
        status = self.request.GET.get('status')
        if search:
            qs = qs.filter(Q(order_number__icontains=search) | Q(address__full_name__icontains=search) | Q(address__phone__icontains=search))
        if status:
            qs = qs.filter(status=status)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'orders'
        context['search_query'] = self.request.GET.get('search', '')
        context['filter_status'] = self.request.GET.get('status', '')
        context['status_choices'] = Order.Status.choices
        return context

class OrderDetailView(StaffRequiredMixin, DetailView):
    model = Order
    template_name = 'admin/order_detail.html'
    context_object_name = 'order'
    slug_field = 'order_number'
    slug_url_kwarg = 'order_number'

    def get_queryset(self):
        return Order.objects.select_related('address', 'payment').prefetch_related(
            'items__product',
            'items__combo',
            'items__selected_variant',
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'orders'
        context['status_choices'] = Order.Status.choices
        context['shipment'] = getattr(self.object, 'shipment', None)
        return context

class OrderInvoiceView(StaffRequiredMixin, DetailView):
    model = Order
    template_name = 'admin/order_invoice.html'
    context_object_name = 'order'
    slug_field = 'order_number'
    slug_url_kwarg = 'order_number'

    def get_queryset(self):
        return Order.objects.select_related('address', 'payment').prefetch_related(
            'items__product',
            'items__combo',
            'items__selected_variant',
        )

class OrderUpdateStatusView(StaffRequiredMixin, View):

    def post(self, request, order_number):
        order = get_object_or_404(Order, order_number=order_number)
        new_status = request.POST.get('status')
        old_status = order.status
        if new_status not in dict(Order.Status.choices):
            messages.error(request, 'Invalid status.')
            return redirect('admin_panel:order_detail', order_number=order_number)
        if new_status == Order.Status.CANCELLED and order.status == Order.Status.DELIVERED:
            messages.error(request, 'Cannot cancel an order that has already been delivered.')
            return redirect('admin_panel:order_detail', order_number=order_number)
        if new_status == Order.Status.CANCELLED:
            shipment = getattr(order, 'shipment', None)
            if shipment and (not shipment.is_cancelled):
                try:
                    shiprocket_service.cancel_shipment(shipment)
                    shipment.is_cancelled = True
                    shipment.cancelled_at = timezone.now()
                    shipment.current_status = 'cancelled'
                    shipment.save(update_fields=['is_cancelled', 'cancelled_at', 'current_status', 'updated_at'])
                except ShiprocketAPIError as exc:
                    messages.error(request, f'Failed to cancel shipment in Shiprocket: {exc}')
                    return redirect('admin_panel:order_detail', order_number=order_number)
                except Exception as exc:
                    logger.error('Unexpected error cancelling shipment for order %s via status update: %s', order_number, exc, exc_info=True)
                    messages.error(request, 'Unexpected error while cancelling shipment.')
                    return redirect('admin_panel:order_detail', order_number=order_number)
        order.status = new_status
        order.save(update_fields=['status'])
        messages.success(request, f'Order status updated to {order.get_status_display()}.')
        try:
            if new_status in (Order.Status.CONFIRMED, Order.Status.SHIPPED, Order.Status.DELIVERED, Order.Status.CANCELLED) and new_status != old_status:
                send_order_confirmation_email_async(order)
        except Exception:
            pass
        return redirect('admin_panel:order_detail', order_number=order_number)

def _normalize_tracking_response(data):
    out = {'status': '', 'eta': '', 'activities': []}
    if not data:
        return out
    tracking_data = data.get('tracking_data') or data
    shipment_tracks = tracking_data.get('shipment_track') or []
    if isinstance(shipment_tracks, dict):
        shipment_tracks = [shipment_tracks]
    if not shipment_tracks:
        out['status'] = tracking_data.get('current_status') or data.get('current_status') or ''
        out['eta'] = tracking_data.get('etd') or tracking_data.get('eta') or tracking_data.get('estimated_delivery_date') or ''
        out['activities'] = tracking_data.get('shipment_track_activities') or tracking_data.get('activities') or tracking_data.get('tracking_history') or []
        return out
    first = shipment_tracks[0] if shipment_tracks else {}
    out['status'] = first.get('current_status') or first.get('status') or tracking_data.get('current_status') or ''
    out['eta'] = first.get('etd') or first.get('eta') or first.get('estimated_delivery_date') or ''
    raw_activities = first.get('shipment_track_activities') or first.get('activities') or first.get('tracking_history') or []
    for a in raw_activities:
        if isinstance(a, dict):
            out['activities'].append({'date': a.get('date') or a.get('event_date') or a.get('timestamp') or '', 'activity': a.get('activity') or a.get('status') or a.get('description') or '', 'location': a.get('location') or a.get('city') or ''})
        else:
            out['activities'].append({'date': '', 'activity': str(a), 'location': ''})
    return out

class OrderShipmentRefreshTrackingView(StaffRequiredMixin, View):

    def post(self, request, order_number):
        if not delivery_enabled():
            messages.error(request, 'Shipment tracking is disabled.')
            return redirect('admin_panel:order_detail', order_number=order_number)
        order = get_object_or_404(Order, order_number=order_number)
        shipment = getattr(order, 'shipment', None)
        if not shipment:
            messages.error(request, 'No shipment found for this order.')
            return redirect('admin_panel:order_detail', order_number=order_number)
        if shipment.is_cancelled:
            messages.error(request, 'Cannot refresh tracking for a cancelled shipment.')
            return redirect('admin_panel:order_detail', order_number=order_number)
        if not shipment.awb_code:
            messages.error(request, 'No AWB code available to track.')
            return redirect('admin_panel:order_detail', order_number=order_number)
        try:
            data = shiprocket_service.track_shipment(shipment.awb_code)
            tracking = _normalize_tracking_response(data)
            shipment.current_status = tracking.get('status') or shipment.current_status
            shipment.tracking_data = {'status': tracking.get('status'), 'eta': tracking.get('eta'), 'activities': tracking.get('activities'), 'awb_code': shipment.awb_code, 'order_id': order_number}
            shipment.save(update_fields=['current_status', 'tracking_data', 'updated_at'])
            messages.success(request, 'Tracking data updated from Shiprocket.')
        except ShiprocketAPIError as exc:
            messages.error(request, f'Failed to fetch tracking: {exc}')
        except Exception as exc:
            logger.error('Unexpected error refreshing tracking for order %s: %s', order_number, exc, exc_info=True)
            messages.error(request, 'An error occurred while refreshing tracking.')
        return redirect('admin_panel:order_detail', order_number=order_number)

class MessageListView(StaffRequiredMixin, ListView):
    model = ContactMessage
    template_name = 'admin/message_list.html'
    context_object_name = 'contact_messages'
    paginate_by = 20

    def get_queryset(self):
        qs = ContactMessage.objects.all()
        status = self.request.GET.get('status')
        if status == 'unresolved':
            qs = qs.filter(is_resolved=False)
        elif status == 'resolved':
            qs = qs.filter(is_resolved=True)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'messages'
        context['filter_status'] = self.request.GET.get('status', '')
        return context

class MessageToggleResolvedView(StaffRequiredMixin, View):

    def post(self, request, pk):
        message = get_object_or_404(ContactMessage, pk=pk)
        message.is_resolved = not message.is_resolved
        message.save(update_fields=['is_resolved'])
        status_text = 'resolved' if message.is_resolved else 'unresolved'
        messages.success(request, f'Message marked as {status_text}.')
        return redirect('admin_panel:message_list')

class S3FileUploadView(StaffRequiredMixin, View):

    def post(self, request):
        import logging
        logger = logging.getLogger(__name__)
        try:
            if 'file' not in request.FILES:
                return JsonResponse({'success': False, 'error': 'No file provided'}, status=400)
            file = request.FILES['file']
            upload_path = request.POST.get('upload_path', 'uploads')
            logger.info(f'Uploading file: {file.name}, size: {file.size}, type: {file.content_type}')
            max_size = 5 * 1024 * 1024
            if file.size > max_size:
                return JsonResponse({'success': False, 'error': f'File size exceeds 5MB limit. Current size: {file.size / (1024 * 1024):.2f}MB'}, status=400)
            allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
            if file.content_type not in allowed_types:
                return JsonResponse({'success': False, 'error': f'Invalid file type. Allowed: JPG, PNG, GIF, WebP'}, status=400)
            from django.core.files.storage import default_storage
            from django.utils.text import slugify
            from django.conf import settings
            import os
            from datetime import datetime
            ext = os.path.splitext(file.name)[1].lower()
            base_name = slugify(os.path.splitext(file.name)[0])
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'{base_name}_{timestamp}{ext}'
            file_path = f'{upload_path}/{filename}'
            logger.info(f'Saving to: {file_path}')
            if settings.USE_S3:
                from custom_storage import MediaFileStorage
                storage = MediaFileStorage()
                saved_path = storage.save(file_path, file)
                file_url = storage.url(saved_path)
            else:
                saved_path = default_storage.save(file_path, file)
                file_url = default_storage.url(saved_path)
            logger.info(f'File saved to: {saved_path}')
            logger.info(f'File URL: {file_url}')
            if settings.USE_S3:
                exists = storage.exists(saved_path)
            else:
                exists = default_storage.exists(saved_path)
            if not exists:
                logger.error(f'File not found after upload: {saved_path}')
                return JsonResponse({'success': False, 'error': 'Upload failed - file not found after upload'}, status=500)
            return JsonResponse({'success': True, 'file_path': saved_path, 'file_url': file_url, 'file_name': filename, 'file_size': file.size})
        except Exception as e:
            logger.error(f'Upload error: {str(e)}', exc_info=True)
            return JsonResponse({'success': False, 'error': f'Upload failed: {str(e)}'}, status=500)

class DealOfDayListView(StaffRequiredMixin, TemplateView):
    template_name = 'admin/deals_list.html'

    def dispatch(self, request, *args, **kwargs):
        if not getattr(settings, 'HOME_DEAL_OF_DAY_ENABLED', True):
            messages.error(request, 'Deal Of The Day management is disabled in settings.')
            return redirect('admin_panel:dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = Product.objects.select_related('category').order_by('category__name', 'name')
        search = (self.request.GET.get('q') or '').strip()
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(category__name__icontains=search))
        current_only = self.request.GET.get('current')
        if current_only == '1':
            today = timezone.now().date()
            qs = qs.filter(Q(is_deal_of_day=True, deal_of_day_start__lte=today, deal_of_day_end__gte=today) | Q(is_deal_of_day=True, deal_of_day_start__isnull=True, deal_of_day_end__isnull=True))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        paginator = Paginator(qs, 20)
        page = self.request.GET.get('page')
        try:
            page_obj = paginator.page(page)
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)
        context['active_menu'] = 'deals'
        context['products'] = page_obj.object_list
        context['page_obj'] = page_obj
        context['paginator'] = paginator
        context['is_paginated'] = paginator.num_pages > 1
        context['search_query'] = (self.request.GET.get('q') or '').strip()
        today = timezone.now().date()
        context['today'] = today
        context['filter_current'] = self.request.GET.get('current') == '1'
        if context['filter_current']:
            context['active_deals_count'] = paginator.count
        else:
            current_deals_qs = Product.objects.filter(Q(is_deal_of_day=True, deal_of_day_start__lte=today, deal_of_day_end__gte=today) | Q(is_deal_of_day=True, deal_of_day_start__isnull=True, deal_of_day_end__isnull=True))
            context['active_deals_count'] = current_deals_qs.count()
        return context

    def post(self, request, *args, **kwargs):
        products = self.get_queryset()
        updated_count = 0
        for product in products:
            prefix = f'p{product.pk}_'
            is_deal_flag = request.POST.get(f'is_deal_{product.pk}') == 'on'
            start_raw = request.POST.get(f'start_{product.pk}') or ''
            end_raw = request.POST.get(f'end_{product.pk}') or ''
            start_date = parse_date(start_raw) if start_raw else None
            end_date = parse_date(end_raw) if end_raw else None
            changed = product.is_deal_of_day != is_deal_flag or product.deal_of_day_start != start_date or product.deal_of_day_end != end_date
            if not changed:
                continue
            product.is_deal_of_day = is_deal_flag
            product.deal_of_day_start = start_date
            product.deal_of_day_end = end_date
            product.save(update_fields=['is_deal_of_day', 'deal_of_day_start', 'deal_of_day_end'])
            updated_count += 1
        if updated_count:
            messages.success(request, f'Updated deals for {updated_count} product(s).')
        else:
            messages.info(request, 'No changes were made.')
        return redirect('admin_panel:deal_list')

class ReviewListView(StaffRequiredMixin, TemplateView):
    template_name = 'admin/review_list.html'
    paginate_by = 25

    def dispatch(self, request, *args, **kwargs):
        if not getattr(settings, 'REVIEW_ENABLED', True):
            raise Http404('Reviews are not enabled.')
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = Review.objects.select_related('product', 'user', 'order').filter(is_deleted=False)
        request = self.request
        q = (request.GET.get('q') or '').strip()
        product_id = request.GET.get('product')
        rating = request.GET.get('rating')
        status = request.GET.get('status')
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        if q:
            qs = qs.filter(Q(product__name__icontains=q) | Q(user__username__icontains=q) | Q(user__email__icontains=q))
        if product_id:
            try:
                qs = qs.filter(product_id=int(product_id))
            except (TypeError, ValueError):
                pass
        if rating:
            try:
                qs = qs.filter(rating=int(rating))
            except (TypeError, ValueError):
                pass
        if status == 'approved':
            qs = qs.filter(is_approved=True)
        elif status == 'unapproved':
            qs = qs.filter(is_approved=False)
        if date_from:
            try:
                df = parse_date(date_from)
                if df:
                    qs = qs.filter(created_at__date__gte=df)
            except Exception:
                pass
        if date_to:
            try:
                dt = parse_date(date_to)
                if dt:
                    qs = qs.filter(created_at__date__lte=dt)
            except Exception:
                pass
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        paginator = Paginator(qs, self.paginate_by)
        page_number = self.request.GET.get('page')
        try:
            page_obj = paginator.page(page_number)
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)
        context['active_menu'] = 'reviews'
        context['reviews'] = page_obj.object_list
        context['page_obj'] = page_obj
        context['paginator'] = paginator
        context['is_paginated'] = paginator.num_pages > 1
        context['products'] = Product.objects.order_by('name').only('id', 'name')
        context['filter_q'] = (self.request.GET.get('q') or '').strip()
        context['filter_product'] = self.request.GET.get('product') or ''
        context['filter_rating'] = self.request.GET.get('rating') or ''
        context['filter_status'] = self.request.GET.get('status') or ''
        context['filter_date_from'] = self.request.GET.get('date_from') or ''
        context['filter_date_to'] = self.request.GET.get('date_to') or ''
        return context


class DashboardBlogListView(StaffRequiredMixin, ListView):
    model = BlogPost
    template_name = 'dashboard/blog/list.html'
    context_object_name = 'posts'
    paginate_by = 20

    def get_queryset(self):
        qs = BlogPost.objects.all()
        status = (self.request.GET.get('status') or '').strip().lower()
        q = (self.request.GET.get('q') or '').strip()
        if status == 'published':
            qs = qs.filter(is_published=True)
        elif status == 'draft':
            qs = qs.filter(is_published=False)
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(slug__icontains=q) | Q(excerpt__icontains=q))
        return qs.order_by('-published_at', '-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'blog'
        context['filter_status'] = (self.request.GET.get('status') or '').strip()
        context['filter_q'] = (self.request.GET.get('q') or '').strip()
        return context


class DashboardBlogCreateView(StaffRequiredMixin, CreateView):
    model = BlogPost
    form_class = BlogPostForm
    template_name = 'dashboard/blog/form.html'
    success_url = reverse_lazy('admin_panel:blog_list')

    def form_valid(self, form):
        obj = form.save(commit=False)
        if obj.is_published and not obj.published_at:
            obj.published_at = timezone.now()
        if (not obj.is_published):
            obj.published_at = None
        obj.save()
        messages.success(self.request, 'Blog post created.')
        return redirect(self.success_url)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'blog'
        context['form_title'] = 'Create blog post'
        return context


class DashboardBlogUpdateView(StaffRequiredMixin, UpdateView):
    model = BlogPost
    form_class = BlogPostForm
    template_name = 'dashboard/blog/form.html'
    success_url = reverse_lazy('admin_panel:blog_list')

    def form_valid(self, form):
        obj = form.save(commit=False)
        if obj.is_published and not obj.published_at:
            obj.published_at = timezone.now()
        if (not obj.is_published):
            obj.published_at = None
        obj.save()
        messages.success(self.request, 'Blog post updated.')
        return redirect(self.success_url)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'blog'
        context['form_title'] = 'Edit blog post'
        return context


class DashboardBlogTogglePublishView(StaffRequiredMixin, View):

    def post(self, request, pk):
        post = get_object_or_404(BlogPost, pk=pk)
        post.is_published = not bool(post.is_published)
        if post.is_published and not post.published_at:
            post.published_at = timezone.now()
        if not post.is_published:
            post.published_at = None
        post.save(update_fields=['is_published', 'published_at', 'updated_at'])
        messages.success(request, 'Publish status updated.')
        return redirect('admin_panel:blog_list')


class DashboardReelListView(StaffRequiredMixin, ListView):
    model = Reel
    template_name = 'dashboard/reels/list.html'
    context_object_name = 'reels'
    paginate_by = 30

    def get_queryset(self):
        qs = Reel.objects.select_related('product').all()
        status = (self.request.GET.get('status') or '').strip().lower()
        if status == 'active':
            qs = qs.filter(is_active=True)
        elif status == 'inactive':
            qs = qs.filter(is_active=False)
        q = (self.request.GET.get('q') or '').strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(caption__icontains=q) | Q(product__name__icontains=q))
        return qs.order_by('display_order', '-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'reels'
        context['filter_status'] = (self.request.GET.get('status') or '').strip()
        context['filter_q'] = (self.request.GET.get('q') or '').strip()
        return context


class DashboardReelCreateView(StaffRequiredMixin, CreateView):
    model = Reel
    form_class = ReelForm
    template_name = 'dashboard/reels/form.html'
    success_url = reverse_lazy('admin_panel:reel_list')

    def form_valid(self, form):
        form.save()
        from django.core.cache import caches
        _cache = caches['locmem'] if 'locmem' in caches else caches['default']
        _cache.delete('home_reels_v1')
        messages.success(self.request, 'Reel created.')
        return redirect(self.success_url)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'reels'
        context['form_title'] = 'Create reel'
        return context


class DashboardReelUpdateView(StaffRequiredMixin, UpdateView):
    model = Reel
    form_class = ReelForm
    template_name = 'dashboard/reels/form.html'
    success_url = reverse_lazy('admin_panel:reel_list')

    def form_valid(self, form):
        form.save()
        from django.core.cache import caches
        _cache = caches['locmem'] if 'locmem' in caches else caches['default']
        _cache.delete('home_reels_v1')
        messages.success(self.request, 'Reel updated.')
        return redirect(self.success_url)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'reels'
        context['form_title'] = 'Edit reel'
        return context


class DashboardReelToggleActiveView(StaffRequiredMixin, View):

    def post(self, request, pk):
        reel = get_object_or_404(Reel, pk=pk)
        reel.is_active = not bool(reel.is_active)
        reel.save(update_fields=['is_active', 'updated_at'])
        from django.core.cache import caches
        _cache = caches['locmem'] if 'locmem' in caches else caches['default']
        _cache.delete('home_reels_v1')
        messages.success(request, 'Reel status updated.')
        return redirect('admin_panel:reel_list')

class ReviewBulkActionView(StaffRequiredMixin, View):

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        action = request.POST.get('action')
        ids = request.POST.getlist('selected')
        if not action or not ids:
            messages.warning(request, 'Please select at least one review and an action.')
            return redirect('admin_panel:review_list')
        try:
            ids_int = [int(x) for x in ids]
        except (TypeError, ValueError):
            messages.error(request, 'Invalid review selection.')
            return redirect('admin_panel:review_list')
        reviews = list(
            Review.objects.select_for_update()
            .select_related('product')
            .filter(id__in=ids_int)
        )
        if not reviews:
            messages.info(request, 'No reviews found for the selected IDs.')
            return redirect('admin_panel:review_list')
        updated_products = set()
        if action == 'approve':
            for r in reviews:
                if not r.is_approved and not r.is_deleted:
                    r.is_approved = True
                    r.save(update_fields=['is_approved'])
                    updated_products.add(r.product_id)
            messages.success(request, 'Selected reviews have been approved.')
        elif action == 'unapprove':
            for r in reviews:
                if r.is_approved and not r.is_deleted:
                    r.is_approved = False
                    r.save(update_fields=['is_approved'])
                    updated_products.add(r.product_id)
            messages.success(request, 'Selected reviews have been unapproved.')
        elif action == 'delete':
            for r in reviews:
                if not r.is_deleted:
                    r.is_deleted = True
                    r.save(update_fields=['is_deleted'])
                    updated_products.add(r.product_id)
            messages.success(request, 'Selected reviews have been deleted.')
        else:
            messages.error(request, 'Unknown action.')
        return redirect('admin_panel:review_list')

class ShipmentRetryView(StaffRequiredMixin, View):

    def post(self, request, order_number):
        if not delivery_enabled():
            messages.error(request, 'Shipment creation is disabled.')
            return redirect('admin_panel:order_detail', order_number=order_number)
        order = get_object_or_404(Order, order_number=order_number)
        shipment = getattr(order, 'shipment', None)
        if order.status == Order.Status.DELIVERED:
            messages.error(request, 'Cannot recreate shipment for a delivered order.')
            return redirect('admin_panel:order_detail', order_number=order_number)
        if shipment is None:
            shipment = Shipment.objects.create(order=order, current_status='pending_creation')
        try:
            create_shipment_for_order(order, shipment)
            messages.success(request, 'Shipment successfully (re)created with Shiprocket.')
        except ShiprocketAPIError as exc:
            shipment.error_log = str(exc)
            shipment.current_status = 'error'
            shipment.save(update_fields=['error_log', 'current_status', 'updated_at'])
            messages.error(request, f'Shiprocket error while creating shipment: {exc}')
        except Exception as exc:
            shipment.error_log = str(exc)
            shipment.current_status = 'error'
            shipment.save(update_fields=['error_log', 'current_status', 'updated_at'])
            logger.error('Unexpected error in ShipmentRetryView for order %s: %s', order_number, exc, exc_info=True)
            messages.error(request, 'Unexpected error while creating shipment.')
        return redirect('admin_panel:order_detail', order_number=order_number)

class ShipmentCancelView(StaffRequiredMixin, View):

    def post(self, request, order_number):
        if not delivery_enabled():
            messages.error(request, 'Shipment cancellation is disabled.')
            return redirect('admin_panel:order_detail', order_number=order_number)
        order = get_object_or_404(Order, order_number=order_number)
        shipment = getattr(order, 'shipment', None)
        if not shipment:
            messages.error(request, 'No shipment found for this order.')
            return redirect('admin_panel:order_detail', order_number=order_number)
        if order.status == Order.Status.DELIVERED:
            messages.error(request, 'Cannot cancel a delivered order.')
            return redirect('admin_panel:order_detail', order_number=order_number)
        if shipment.is_cancelled:
            messages.info(request, 'Shipment is already marked as cancelled.')
            return redirect('admin_panel:order_detail', order_number=order_number)
        try:
            shiprocket_service.cancel_shipment(shipment)
            shipment.is_cancelled = True
            shipment.cancelled_at = timezone.now()
            shipment.current_status = 'cancelled'
            shipment.save(update_fields=['is_cancelled', 'cancelled_at', 'current_status', 'updated_at'])
            order.status = Order.Status.CANCELLED
            order.save(update_fields=['status', 'updated_at'])
            messages.success(request, 'Shipment cancelled and order marked as cancelled.')
        except ShiprocketAPIError as exc:
            messages.error(request, f'Failed to cancel shipment in Shiprocket: {exc}')
        except Exception as exc:
            logger.error('Unexpected error cancelling shipment for order %s: %s', order_number, exc, exc_info=True)
            messages.error(request, 'Unexpected error while cancelling shipment.')
        return redirect('admin_panel:order_detail', order_number=order_number)

class ProductDeliveryStatesUpdateView(View):
    """
    POST endpoint called from the product edit page delivery-states section.
    Atomically replaces the product's delivery state list.
 
    POST /admin/products/<pk>/delivery-states/
    """
 
    def post(self, request, pk):
        from app.models import Product
        from app.admin_forms import ProductDeliveryStateForm
 
        product = get_object_or_404(Product, pk=pk)
        form = ProductDeliveryStateForm(request.POST, product=product)
 
        if form.is_valid():
            form.save()
            messages.success(request, "Delivery states updated successfully.")
        else:
            for field, errs in form.errors.items():
                for err in errs:
                    messages.error(request, f"{field}: {err}")
 
        return redirect("admin_panel:product_edit", pk=product.pk)


class DeliveryChargesView(StaffRequiredMixin, View):
    """
    Centralized delivery-charge management: one fixed charge per state,
    applied to every product. GET renders the page, POST saves all charges.

    GET/POST /admin/delivery-charges/
    """

    template_name = 'admin/delivery_charges.html'

    def get(self, request):
        from app.admin_forms import StateDeliveryChargeForm

        form = StateDeliveryChargeForm()
        return render(request, self.template_name, {
            'active_menu': 'delivery_charges',
            'form_title': 'Delivery Charges',
            'charge_form': form,
        })

    def post(self, request):
        from app.admin_forms import StateDeliveryChargeForm

        form = StateDeliveryChargeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Delivery charges updated successfully.')
            return redirect('admin_panel:delivery_charges')

        for field, errs in form.errors.items():
            for err in errs:
                messages.error(request, f'{field}: {err}')
        return render(request, self.template_name, {
            'active_menu': 'delivery_charges',
            'form_title': 'Delivery Charges',
            'charge_form': form,
        })


class TestimonialListView(StaffRequiredMixin, ListView):
    model               = Testimonial        # imported from .models
    template_name       = 'dashboard/testimonials/list.html'
    context_object_name = 'testimonials'
    paginate_by         = 20
 
    def get_queryset(self):
        qs     = Testimonial.objects.all()
        status = (self.request.GET.get('status') or '').strip().lower()
        if status == 'active':
            qs = qs.filter(is_active=True)
        elif status == 'inactive':
            qs = qs.filter(is_active=False)
        return qs.order_by('display_order', '-created_at')
 
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu']   = 'testimonials'
        context['filter_status'] = self.request.GET.get('status', '')
        return context
 
 
class TestimonialCreateView(StaffRequiredMixin, CreateView):
    model         = Testimonial
    form_class    = TestimonialForm          # imported from .admin_forms
    template_name = 'dashboard/testimonials/form.html'
    success_url   = reverse_lazy('admin_panel:testimonial_list')
 
    def form_valid(self, form):
        messages.success(self.request, 'Testimonial created successfully.')
        return super().form_valid(form)
 
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'testimonials'
        context['form_title']  = 'Add Testimonial'
        return context
 
 
class TestimonialUpdateView(StaffRequiredMixin, UpdateView):
    model         = Testimonial
    form_class    = TestimonialForm
    template_name = 'dashboard/testimonials/form.html'
    success_url   = reverse_lazy('admin_panel:testimonial_list')
 
    def form_valid(self, form):
        messages.success(self.request, 'Testimonial updated successfully.')
        return super().form_valid(form)
 
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'testimonials'
        context['form_title']  = f'Edit: {self.object.name}'
        return context
 
 
class TestimonialDeleteView(StaffRequiredMixin, DeleteView):
    model       = Testimonial
    success_url = reverse_lazy('admin_panel:testimonial_list')
 
    def post(self, request, *args, **kwargs):
        obj  = self.get_object()
        name = obj.name
 
        # Clean up the photo file from storage to avoid orphaned files
        if obj.photo:
            try:
                photo_name = obj.photo.name
                storage    = obj.photo.storage
                Testimonial.objects.filter(pk=obj.pk).update(photo=None)
                try:
                    storage.delete(photo_name)
                except Exception:
                    pass
            except Exception as e:
                logger.warning('Failed to delete testimonial photo: %s', e)
 
        try:
            Testimonial.objects.filter(pk=obj.pk).delete()
            messages.success(request, f"Testimonial by '{name}' deleted.")
        except Exception as e:
            messages.error(request, f'Error deleting testimonial: {e}')
 
        return redirect(self.success_url)
 
 
class TestimonialToggleActiveView(StaffRequiredMixin, View):
    """Quick active/inactive toggle from the list page."""
 
    def post(self, request, pk):
        testimonial            = get_object_or_404(Testimonial, pk=pk)
        testimonial.is_active  = not testimonial.is_active
        testimonial.save(update_fields=['is_active', 'updated_at'])
        state = 'activated' if testimonial.is_active else 'deactivated'
        messages.success(request, f'Testimonial {state}.')
        return redirect('admin_panel:testimonial_list')


class CouponListView(StaffRequiredMixin, ListView):
    model = Coupon
    template_name = 'dashboard/coupons/list.html'
    context_object_name = 'coupons'
    paginate_by = 25

    def get_queryset(self):
        qs = Coupon.objects.all()
        status = self.request.GET.get('status') or ''
        if status == 'active':
            qs = qs.filter(is_active=True)
        elif status == 'inactive':
            qs = qs.filter(is_active=False)
        q = (self.request.GET.get('q') or '').strip()
        if q:
            qs = qs.filter(Q(code__icontains=q) | Q(description__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'coupons'
        context['filter_status'] = self.request.GET.get('status') or ''
        context['q'] = self.request.GET.get('q') or ''
        return context


class CouponCreateView(StaffRequiredMixin, CreateView):
    model = Coupon
    form_class = CouponForm
    template_name = 'dashboard/coupons/form.html'
    success_url = reverse_lazy('admin_panel:coupon_list')

    def form_valid(self, form):
        messages.success(self.request, f'Coupon {form.instance.code} created.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'coupons'
        context['form_title'] = 'Create coupon'
        return context


class CouponUpdateView(StaffRequiredMixin, UpdateView):
    model = Coupon
    form_class = CouponForm
    template_name = 'dashboard/coupons/form.html'
    success_url = reverse_lazy('admin_panel:coupon_list')

    def form_valid(self, form):
        messages.success(self.request, f'Coupon {form.instance.code} updated.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'coupons'
        context['form_title'] = f'Edit {self.object.code}'
        return context


class CouponToggleActiveView(StaffRequiredMixin, View):
    def post(self, request, pk):
        coupon = get_object_or_404(Coupon, pk=pk)
        coupon.is_active = not coupon.is_active
        coupon.save(update_fields=['is_active', 'updated_at'])
        state = 'enabled' if coupon.is_active else 'disabled'
        messages.success(request, f'Coupon {coupon.code} {state}.')
        return redirect('admin_panel:coupon_list')


class CouponRedemptionListView(StaffRequiredMixin, ListView):
    model = CouponRedemption
    template_name = 'dashboard/coupons/redemptions.html'
    context_object_name = 'redemptions'
    paginate_by = 40

    def get_queryset(self):
        self.coupon = get_object_or_404(Coupon, pk=self.kwargs['pk'])
        return (
            CouponRedemption.objects.filter(coupon=self.coupon)
            .select_related('order', 'user')
            .order_by('-created_at')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'coupons'
        context['coupon'] = self.coupon
        return context
 