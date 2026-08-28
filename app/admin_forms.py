import logging
from django import forms
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.forms.formsets import DELETION_FIELD_NAME
from .models import Banner, BlogPost, Category, Combo, Coupon, Product, HomeCategory, HomeCategoryProduct, Reel, Testimonial
from .models import RentalConfig
logger = logging.getLogger(__name__)

def _validate_image_file(image, required=False):
    if not image and (not required):
        return image
    if image and hasattr(image, 'size'):
        max_size = 5 * 1024 * 1024
        if image.size > max_size:
            raise forms.ValidationError(f'Image file size cannot exceed 5MB. Current size: {image.size / (1024 * 1024):.2f}MB')
        try:
            from PIL import Image as PILImage
            img = PILImage.open(image)
            width, height = img.size
            if width * height > 5000000:
                raise forms.ValidationError('Image resolution cannot exceed 5 megapixels. Please resize or compress.')
            img.verify()
            image.seek(0)
        except forms.ValidationError:
            raise
        except Exception:
            raise forms.ValidationError('Invalid image file. Please upload a valid image (JPG, PNG, GIF, WebP).')
    return image

class AdminLoginForm(forms.Form):
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username', 'autocomplete': 'username'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password', 'autocomplete': 'current-password'}))

class CategoryForm(forms.ModelForm):

    class Meta:
        model = Category
        fields = ['name', 'parent', 'slug', 'is_active', 'image', 'banner_image', 'banner_tagline']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Category Name'}),
            'parent': forms.Select(attrs={'class': 'form-control'}),
            'slug': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'category-slug'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'image': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'banner_image': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'banner_tagline': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional — shown on shop banner'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['slug'].required = False
        if self.instance and self.instance.pk:
            self.fields['parent'].queryset = Category.objects.exclude(pk=self.instance.pk).order_by('name')
        else:
            self.fields['parent'].queryset = Category.objects.all().order_by('name')

    def clean(self):
        cleaned_data = super().clean()
        if self.data.get('clear_image') == 'true':
            cleaned_data['image'] = False
        if self.data.get('clear_banner_image') == 'true':
            cleaned_data['banner_image'] = False
        return cleaned_data

    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            raise forms.ValidationError("Category name is required.")
        
        #case-insensitive unique check
        qs = Category.objects.filter(name__iexact=name)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("A category with this name already exists.")
        return name

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image and hasattr(image, 'size'):
            max_size = 5 * 1024 * 1024
            if image.size > max_size:
                raise forms.ValidationError(f'Image file size cannot exceed 5MB.')
            try:
                from PIL import Image
                img = Image.open(image)
                width, height = img.size
                if width * height > 5000000:
                    raise forms.ValidationError('Image resolution cannot exceed 5 megapixels.')
                img.verify()
                image.seek(0)
            except forms.ValidationError:
                raise
            except Exception:
                raise forms.ValidationError('Invalid image file.')
        return image

    def clean_banner_image(self):
        image = self.cleaned_data.get('banner_image')
        return _validate_banner_image(image, required=False)


def _validate_banner_image(image, required=True):
    if not image and (not required):
        return image
    if not image and required:
        raise forms.ValidationError('Banner image is required.')
    if image and hasattr(image, 'size'):
        max_size = 5 * 1024 * 1024
        if image.size > max_size:
            raise forms.ValidationError(f'Image file size cannot exceed 5MB. Current size: {image.size / (1024 * 1024):.2f}MB')
        try:
            from PIL import Image as PILImage
            img = PILImage.open(image)
            width, height = img.size
            if width * height > 5000000:
                raise forms.ValidationError('Image resolution cannot exceed 5 megapixels. Please resize or compress.')
            ratio = width / height
            if not (1.5 <= ratio <= 3.5):
                raise forms.ValidationError(f'Banner image aspect ratio must be between 1.5:1 and 3.5:1. Uploaded image is {ratio:.2f}:1.')
            img.verify()
            image.seek(0)
        except forms.ValidationError:
            raise
        except Exception:
            raise forms.ValidationError('Invalid image file. Please upload a valid image (JPG, PNG, GIF, WebP).')
    return image


class HomeCategoryForm(forms.ModelForm):
    products = forms.ModelMultipleChoiceField(label='Featured products', queryset=Product.objects.none(), required=False, widget=forms.SelectMultiple(attrs={'class': 'form-control', 'size': 12}))

    class Meta:
        model = HomeCategory
        fields = ['name', 'slug', 'description', 'banner_image', 'display_order', 'is_active', 'link_url', 'linked_category']
        widgets = {'name': forms.TextInput(attrs={'class': 'form-control'}), 'slug': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'auto from name if empty'}), 'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}), 'banner_image': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}), 'display_order': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}), 'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}), 'link_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://... (optional)'}), 'linked_category': forms.Select(attrs={'class': 'form-control'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['slug'].required = False
        self.fields['linked_category'].queryset = Category.objects.filter(is_active=True).order_by('name')
        self.fields['linked_category'].required = False
        linked_ids = []
        if self.instance and self.instance.pk:
            linked_ids = list(HomeCategoryProduct.objects.filter(home_category=self.instance).order_by('display_order', 'id').values_list('product_id', flat=True))
            self.initial['products'] = linked_ids
        base_qs = Product.objects.all().order_by('name')
        if linked_ids:
            self.fields['products'].queryset = base_qs.filter(Q(is_active=True) | Q(pk__in=linked_ids))
        else:
            self.fields['products'].queryset = base_qs.filter(is_active=True)

    def clean_banner_image(self):
        image = self.cleaned_data.get('banner_image')
        if image and hasattr(image, 'size'):
            return _validate_banner_image(image, required=False)
        if not image and (not self.instance.pk or not self.instance.banner_image):
            raise forms.ValidationError('Banner image is required.')
        return image

    def clean_link_url(self):
        url = self.cleaned_data.get('link_url')
        if url is not None and str(url).strip() == '':
            return None
        return url

    def save(self, commit=True):
        instance = super().save(commit=commit)
        if not commit:
            return instance
        cleaned_products = self.cleaned_data.get('products')
        cleaned_ids = set(cleaned_products.values_list('pk', flat=True)) if cleaned_products else set()
        raw_ids = self.data.getlist('products') if self.is_bound else []
        seen = set()
        ordered_pks = []
        for x in raw_ids:
            try:
                pk = int(x)
            except (TypeError, ValueError):
                continue
            if pk in cleaned_ids and pk not in seen:
                seen.add(pk)
                ordered_pks.append(pk)
        tail = cleaned_ids - seen
        if tail:
            ordered_pks.extend(self.fields['products'].queryset.filter(pk__in=tail).order_by('name').values_list('pk', flat=True))
        with transaction.atomic():
            HomeCategoryProduct.objects.filter(home_category=instance).delete()
            if ordered_pks:
                HomeCategoryProduct.objects.bulk_create([HomeCategoryProduct(home_category=instance, product_id=pk, display_order=i) for i, pk in enumerate(ordered_pks)])
        return instance


class BannerForm(forms.ModelForm):

    class Meta:
        model = Banner
        fields = ['title', 'subtitle', 'image', 'redirect_url', 'is_active', 'display_order']
        widgets = {'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Banner title (optional)'}), 'subtitle': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Banner subtitle (optional)'}), 'image': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}), 'redirect_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://... (optional)'}), 'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}), 'display_order': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'placeholder': '0'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['title'].required = False
        self.fields['subtitle'].required = False
        self.fields['redirect_url'].required = False
        if self.instance and self.instance.pk and self.instance.image:
            self.fields['image'].required = False

    def clean_image(self):
        image = self.cleaned_data.get('image')
        required = not (self.instance and self.instance.pk and getattr(self.instance, 'image', None))
        return _validate_banner_image(image, required=required)

    def clean_redirect_url(self):
        url = self.cleaned_data.get('redirect_url')
        if url is not None and str(url).strip() == '':
            return None
        return url

    def clean_is_active(self):
        is_active = self.cleaned_data.get('is_active')
        if is_active:
            from .models import Banner
            active_count = Banner.objects.filter(is_active=True).count()
            if self.instance and self.instance.pk and self.instance.is_active:
                pass
            elif active_count >= Banner.MAX_ACTIVE:
                raise forms.ValidationError(f"Maximum {Banner.MAX_ACTIVE} banners can be active at a time.")
        return is_active
BASIC_EDIT_FIELDS = ['category', 'name', 'slug', 'description', 'brand', 'base_price', 'base_original_price', 'base_stock', 'is_featured', 'is_bestseller', 'is_deal_of_day', 'deal_of_day_start', 'deal_of_day_end', 'is_active', 'is_gst_applicable', 'gst_percentage', 'hsn_code', 'is_rent_available', 'purchase_enabled', 'is_plant_combo', 'care_instructions', 'sunlight', 'watering', 'difficulty', 'plant_type', 'maintenance_notes']

class ProductBasicEditForm(forms.ModelForm):

    class Meta:
        model = Product
        fields = BASIC_EDIT_FIELDS
        widgets = {'category': forms.Select(attrs={'class': 'form-control'}), 'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Product Name'}), 'slug': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'product-slug'}), 'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}), 'brand': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Brand'}), 'base_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'placeholder': '0.00', 'id': 'basic-base_price'}), 'base_original_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'placeholder': 'MRP / Original price (optional)', 'id': 'basic-base_original_price'}), 'base_stock': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'placeholder': '0', 'id': 'basic-base_stock'}), 'is_featured': forms.CheckboxInput(attrs={'class': 'form-check-input'}), 'is_bestseller': forms.CheckboxInput(attrs={'class': 'form-check-input'}), 'is_deal_of_day': forms.CheckboxInput(attrs={'class': 'form-check-input'}), 'deal_of_day_start': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}), 'deal_of_day_end': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}), 'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}), 'is_gst_applicable': forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'basic-is_gst_applicable'}), 'gst_percentage': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0–28', 'min': 0, 'max': 28, 'step': '0.01'}), 'hsn_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 8517', 'maxlength': 20}), 'is_rent_available': forms.CheckboxInput(attrs={'class': 'form-check-input'}), 'purchase_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'basic-purchase_enabled'}), 'is_plant_combo': forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'basic-is_plant_combo'}), 'care_instructions': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'id': 'basic-care_instructions', 'placeholder': 'What is included, assembly, delivery notes…'}), 'sunlight': forms.Select(attrs={'class': 'form-control'}), 'watering': forms.Select(attrs={'class': 'form-control'}), 'difficulty': forms.Select(attrs={'class': 'form-control'}), 'plant_type': forms.Select(attrs={'class': 'form-control'}), 'maintenance_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Maintenance tips (Care guide section)'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['slug'].required = False
        self.fields['description'].required = False
        self.fields['brand'].required = False
        self.fields['deal_of_day_start'].required = False
        self.fields['deal_of_day_end'].required = False
        self.fields['gst_percentage'].required = False
        self.fields['hsn_code'].required = False
        self.fields['base_original_price'].required = False
        self.fields['care_instructions'].required = False
        self.fields['maintenance_notes'].required = False
        self.fields['sunlight'].required = False
        self.fields['watering'].required = False
        self.fields['difficulty'].required = False
        self.fields['plant_type'].required = False
        
        #base field strict validation
        self.fields['category'].required = True
        self.fields['category'].error_messages = {'required': 'Category is required.'}
        self.fields['name'].required = True
        self.fields['name'].error_messages = {'required': 'Product name is required.'}
        self.fields['base_price'].required = True
        self.fields['base_price'].error_messages = {'required': 'Selling price is required.'}
        self.fields['base_stock'].required = True
        self.fields['base_stock'].error_messages = {'required': 'Stock is required.'}

        active = Category.objects.filter(is_active=True)
        if self.instance and self.instance.pk and self.instance.category_id:
            current = self.instance.category
            if current and (not current.is_active):
                active = active | Category.objects.filter(pk=current.pk)
        self.fields['category'].queryset = active.order_by('name')

    def clean(self):
        cleaned = super().clean()
        is_gst = cleaned.get('is_gst_applicable')
        gst_pct = cleaned.get('gst_percentage')
        if is_gst:
            if gst_pct is None:
                self.add_error('gst_percentage', 'GST % is required when GST is applicable.')
            else:
                try:
                    pct = float(gst_pct)
                    if pct < 0 or pct > 28:
                        self.add_error('gst_percentage', 'GST % must be between 0 and 28.')
                except (TypeError, ValueError):
                    self.add_error('gst_percentage', 'Enter a valid number.')
            if not cleaned.get('hsn_code'):
                self.add_error('hsn_code', 'HSN Code is required when GST is applicable.')
        elif gst_pct is not None:
            cleaned['gst_percentage'] = None
            
        base_price = cleaned.get('base_price')
        base_original_price = cleaned.get('base_original_price')
        if base_original_price and (not base_price):
            self.add_error('base_price', 'Selling price is required when original price is set.')
        if base_original_price and base_price and (base_original_price <= base_price):
            self.add_error('base_original_price', 'Original/MRP price must be greater than the selling price.')
            
        is_deal = cleaned.get('is_deal_of_day')
        dod_start = cleaned.get('deal_of_day_start')
        dod_end = cleaned.get('deal_of_day_end')
        if is_deal:
            if dod_start and dod_end and dod_end < dod_start:
                self.add_error('deal_of_day_end', 'End date cannot be before start date.')
                
        return cleaned


class BlogPostForm(forms.ModelForm):

    class Meta:
        model = BlogPost
        fields = ['title', 'slug', 'excerpt', 'body', 'cover_image', 'is_published', 'published_at']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Title'}),
            'slug': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'auto from title if empty'}),
            'excerpt': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Optional short excerpt'}),
            'body': forms.Textarea(attrs={'class': 'form-control', 'rows': 14, 'placeholder': 'Blog content'}),
            'cover_image': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'is_published': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'published_at': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['slug'].required = False
        self.fields['excerpt'].required = False
        self.fields['cover_image'].required = False
        self.fields['published_at'].required = False

    def clean_cover_image(self):
        image = self.cleaned_data.get('cover_image')
        return _validate_image_file(image, required=False)


class ReelForm(forms.ModelForm):

    class Meta:
        model = Reel
        fields = ['title', 'product', 'caption', 'video', 'poster_image', 'display_order', 'is_active']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Title (optional)'}),
            'product': forms.Select(attrs={'class': 'form-control'}),
            'caption': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Caption (optional)'}),
            'video': forms.FileInput(attrs={'class': 'form-control', 'accept': 'video/mp4,video/webm,video/quicktime'}),
            'poster_image': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'display_order': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['title'].required = False
        self.fields['caption'].required = False
        self.fields['poster_image'].required = False
        self.fields['display_order'].required = False
        self.fields['product'].queryset = Product.objects.filter(is_active=True).order_by('name')
        self.fields['product'].required = True
        self.fields['product'].empty_label = "Select a product..."
        self.fields['product'].error_messages = {'required': 'A linked product is mandatory for storefront visibility.'}

    def clean_poster_image(self):
        image = self.cleaned_data.get('poster_image')
        image = _validate_image_file(image, required=False)
        if image:
            from django.core.files.uploadedfile import UploadedFile
            if isinstance(image, UploadedFile):
                try:
                    from PIL import Image as PILImage
                    img = PILImage.open(image)
                    width, height = img.size
                    ratio = width / height
                    if not (0.55 <= ratio <= 0.58):
                        raise forms.ValidationError('Poster image must have an approximate 9:16 vertical ratio.')
                    image.seek(0)
                except forms.ValidationError:
                    raise
                except Exception:
                    raise forms.ValidationError('Invalid poster image.')
        return image

    def clean_video(self):
        video = self.cleaned_data.get('video')
        from django.core.files.uploadedfile import UploadedFile
        if not video or not isinstance(video, UploadedFile):
            return video
            
        import tempfile
        import subprocess
        import os
        
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_video:
                for chunk in video.chunks():
                    temp_video.write(chunk)
                temp_path = temp_video.name
            
            cmd = [
                'ffprobe', '-v', 'error', '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height', '-of', 'csv=s=x:p=0',
                temp_path
            ]
            
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode('utf-8').strip()
            if 'x' in output:
                width, height = map(int, output.split('x'))
                ratio = width / height
                if not (0.55 <= ratio <= 0.58):
                    raise forms.ValidationError('Video must have an approximate 9:16 vertical ratio.')
        except forms.ValidationError:
            raise
        except Exception as e:
            logger.error(f"FFprobe failed to validate video: {str(e)}")
            raise forms.ValidationError('Could not validate video format. Please ensure it is a valid video file.')
        finally:
            if 'temp_path' in locals() and os.path.exists(temp_path):
                os.unlink(temp_path)
            video.seek(0)
            
        return video


class RentalConfigForm(forms.ModelForm):

    class Meta:
        model = RentalConfig
        fields = ['is_rent_enabled', 'rent_price_per_day', 'rent_description', 'rent_instructions']
        widgets = {
            'is_rent_enabled': forms.CheckboxInput(attrs={'class': 'toggle-input'}),  # changed
            'rent_price_per_day': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': 0, 'placeholder': '0.00'}),
            'rent_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Short rental description'}),
            'rent_instructions': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Return, care, delivery/collection instructions'}),
        }


class ComboForm(forms.ModelForm):

    class Meta:
        model = Combo
        fields = [
            'name',
            'slug',
            'description',
            'instructions',
            'price',
            'original_price',
            'image',
            'is_active',
            'show_in_combos_nav',
            'purchase_enabled',
            'is_gst_applicable',
            'gst_percentage',
            'hsn_code',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Bundle name'}),
            'slug': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'auto from name if empty'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'instructions': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Inclusions, delivery notes…'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': 0}),
            'original_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': 0, 'placeholder': 'MRP (optional)'}),
            'image': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_in_combos_nav': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'purchase_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_gst_applicable': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'gst_percentage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': 0, 'max': 28}),
            'hsn_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['slug'].required = False
        self.fields['original_price'].required = False
        self.fields['image'].required = False
        self.fields['gst_percentage'].required = False
        self.fields['hsn_code'].required = False

    def clean_image(self):
        return _validate_image_file(self.cleaned_data.get('image'), required=False)

REGION_LABELS = {
    "south":     "South India",
    "west":      "West India",
    "central":   "Central India",
    "east":      "East India",
    "north":     "North India",
    "northeast": "North-East India",
    "ut":        "Union Territories",
}


class ProductDeliveryStateForm(forms.Form):
    """
    Multi-checkbox form: seller picks which states this product delivers to.
    Delivery charges are centralized on the Delivery Charges page, not here.
    """

    states = forms.ModelMultipleChoiceField(
        queryset=None,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Deliverable States",
        help_text=(
            "Tick every state this product can be shipped to. "
            "Since the shop is in Kerala, start with South India. "
            "Delivery charges for each state are set on the Delivery Charges page."
        ),
    )

    def __init__(self, *args, product=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.product = product

        from app.models import DeliveryState
        self.fields["states"].queryset = (
            DeliveryState.objects
            .filter(is_active=True)
            .order_by("display_order", "name")
        )

        if product:
            from app.models import ProductDeliveryState
            current_ids = list(
                ProductDeliveryState.objects
                .filter(product=product)
                .values_list("state_id", flat=True)
            )
            self.fields["states"].initial = current_ids

    def save(self):
        """Atomically replace the product's deliverable states."""
        if not self.product:
            return
        from app.services.state_delivery_service import set_product_delivery_states
        selected = self.cleaned_data.get("states", [])
        set_product_delivery_states(self.product.pk, [s.pk for s in selected])

    def get_states_by_region(self):
        """
        Returns ordered list of (region_label, [DeliveryState, ...]) tuples.
        Used in templates for grouped rendering.
        """
        from app.services.state_delivery_service import get_states_by_region

        grouped = get_states_by_region()
        return [
            (REGION_LABELS.get(region, region), states)
            for region, states in grouped.items()
        ]


class StateDeliveryChargeForm(forms.Form):
    """
    One fixed delivery charge per state, applied to every product.
    Rendered as a grouped-by-region list of charge inputs (charge_<state_id>).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from app.services.state_delivery_service import get_all_active_states

        self.states = list(get_all_active_states())
        for state in self.states:
            self.fields[f"charge_{state.pk}"] = forms.DecimalField(
                required=False,
                min_value=0,
                max_digits=10,
                decimal_places=2,
                label=state.name,
                widget=forms.NumberInput(attrs={
                    "class": "form-control ds-charge-input",
                    "min": "0",
                    "step": "0.01",
                    "inputmode": "decimal",
                    "placeholder": "0.00",
                }),
            )
            if not self.is_bound and state.delivery_charge is not None:
                self.initial[f"charge_{state.pk}"] = state.delivery_charge

    def save(self):
        from app.services.state_delivery_service import set_state_delivery_charges

        charges = {
            state.pk: self.cleaned_data.get(f"charge_{state.pk}")
            for state in self.states
        }
        set_state_delivery_charges(charges)

    def regions_with_fields(self):
        """Returns ordered list of (region_label, [(state, bound_field), ...]) tuples."""
        from app.services.state_delivery_service import get_states_by_region

        grouped = get_states_by_region()
        return [
            (
                REGION_LABELS.get(region, region),
                [(state, self[f"charge_{state.pk}"]) for state in states],
            )
            for region, states in grouped.items()
        ]
 
class TestimonialForm(forms.ModelForm):
 
    class Meta:
        model  = Testimonial         
        fields = [
            'name',
            'photo',
            'rating',
            'description',
            'is_verified',
            'is_active',
            'display_order',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Customer name',
            }),
            'photo': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
            }),
            'rating': forms.Select(attrs={
                'class': 'form-control',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'What did the customer say?',
            }),
            'is_verified': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
            'display_order': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'placeholder': '0',
            }),
        }
 
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['photo'].required       = False
        self.fields['display_order'].required = False
 
    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        return _validate_image_file(photo, required=False)


class CouponForm(forms.ModelForm):
    class Meta:
        model = Coupon
        fields = [
            'code',
            'discount_type',
            'value',
            'min_order_amount',
            'max_discount_amount',
            'starts_at',
            'ends_at',
            'is_active',
            'max_uses',
            'max_uses_per_customer',
            'description',
            'internal_note',
        ]
        widgets = {
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'WELCOME10',
                'style': 'text-transform:uppercase',
            }),
            'discount_type': forms.Select(attrs={'class': 'form-control'}),
            'value': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
            }),
            'min_order_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
            }),
            'max_discount_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
            }),
            'starts_at': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
            }),
            'ends_at': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'max_uses': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'max_uses_per_customer': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'description': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Shown in admin / optional customer note',
            }),
            'internal_note': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['max_discount_amount'].required = False
        self.fields['max_uses'].required = False
        self.fields['max_uses_per_customer'].required = False
        self.fields['starts_at'].required = False
        self.fields['ends_at'].required = False
        self.fields['description'].required = False
        self.fields['internal_note'].required = False
        for name in ('starts_at', 'ends_at'):
            field = self.fields[name]
            field.input_formats = [
                '%Y-%m-%dT%H:%M',
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d %H:%M',
            ]
            if self.instance and getattr(self.instance, name, None):
                field.widget.attrs['value'] = getattr(self.instance, name).strftime('%Y-%m-%dT%H:%M')

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip().upper()
        if not code:
            raise forms.ValidationError('Coupon code is required.')
        qs = Coupon.objects.filter(code=code)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('A coupon with this code already exists.')
        return code

    def clean(self):
        cleaned = super().clean()
        dtype = cleaned.get('discount_type')
        value = cleaned.get('value')
        if dtype == Coupon.DiscountType.PERCENT and value is not None and value > 100:
            self.add_error('value', 'Percentage cannot exceed 100.')
        starts = cleaned.get('starts_at')
        ends = cleaned.get('ends_at')
        if starts and ends and ends < starts:
            self.add_error('ends_at', 'Expiry must be after the start date.')
            
        from django.utils import timezone
        now = timezone.now()
        
        if not self.instance.pk:
            if starts and starts < now - timezone.timedelta(minutes=5):
                self.add_error('starts_at', 'Start date cannot be in the past.')
            if ends and ends < now - timezone.timedelta(minutes=5):
                self.add_error('ends_at', 'Expiry date cannot be in the past.')
        else:
            if 'starts_at' in self.changed_data and starts and starts < now - timezone.timedelta(minutes=5):
                self.add_error('starts_at', 'Start date cannot be changed to a past date.')
            if 'ends_at' in self.changed_data and ends and ends < now - timezone.timedelta(minutes=5):
                self.add_error('ends_at', 'Expiry date cannot be changed to a past date.')
                
        return cleaned