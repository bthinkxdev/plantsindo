from django import forms
from django.core.validators import EmailValidator, RegexValidator
from django.contrib.auth.models import User
from django.utils.dateparse import parse_date
from .models import Address, ContactMessage, NewsletterSubscription, Review
from .delivery_utils import delivery_enabled
from .services.state_delivery_service import get_all_active_states, resolve_delivery_state_id
from .services.cart_order import format_cart_delivery_error, get_cart_delivery_issues


def active_delivery_state_queryset():
    return get_all_active_states()


def configure_delivery_state_field(field, *, widget_class='form-input', empty_label='Select state…'):
    field.queryset = active_delivery_state_queryset()
    field.empty_label = empty_label
    field.label = 'State'
    existing = field.widget.attrs.get('class', '')
    field.widget.attrs['class'] = f'{existing} {widget_class}'.strip()


def sync_state_text_from_delivery_state(cleaned_data):
    ds = cleaned_data.get('delivery_state')
    if ds is not None and hasattr(ds, 'name'):
        cleaned_data['state'] = ds.name
    return cleaned_data

class CartAddForm(forms.Form):
    product_id = forms.IntegerField(min_value=1, required=False)
    combo_id = forms.IntegerField(min_value=1, required=False)
    variant_id = forms.IntegerField(min_value=1, required=False,help_text="Variant ID (optional for simple products)")
    quantity = forms.IntegerField(min_value=1)
    line_type = forms.ChoiceField(choices=[("purchase", "Purchase"), ("rental", "Rental")],required=False, initial="purchase")
    rental_billing = forms.ChoiceField(choices=[("", "—"), ("day", "Day")],required=False, initial="")
    rental_period_count = forms.IntegerField(min_value=1, required=False,help_text="Number of days to rent")
    rental_start_date = forms.CharField(required=False)
    rental_end_date = forms.CharField(required=False)
    is_gift = forms.BooleanField(required=False, initial=False)
    selected_pot_id = forms.IntegerField(min_value=1, required=False,help_text="Optional pot product ID")
 
    def clean(self):
        data = super().clean()
        pid = data.get("product_id")
        cid = data.get("combo_id")
        if pid and cid:
            raise forms.ValidationError("Choose either a product or a combo bundle, not both.")
        if not pid and not cid:
            raise forms.ValidationError("Select a product or combo to add.") 
        lt = (data.get("line_type") or "purchase").strip().lower()
        if lt not in ("purchase", "rental"):
            lt = "purchase"
        data["line_type"] = lt
        if lt == "rental" and cid:
            raise forms.ValidationError("Combo bundles cannot be rented.")
        if lt == "rental":
            # Rentals are per-day only.
            data["rental_billing"] = "day"
            start_raw = (data.get("rental_start_date") or "").strip()
            end_raw   = (data.get("rental_end_date") or "").strip()
            start = parse_date(start_raw) if start_raw else None
            end   = parse_date(end_raw) if end_raw else None
            if not start or not end:
                raise forms.ValidationError("Select rental start and end dates.")
            if end < start:
                raise forms.ValidationError("Rental end date must be on or after start date.")
            # Inclusive days
            days = (end - start).days + 1
            if days < 1:
                raise forms.ValidationError("Invalid rental duration.")
            data["rental_period_count"] = days
            # Pot add-ons are not supported for rentals
            data["selected_pot_id"] = None
        else:
            data["rental_billing"]      = ""
            data["rental_period_count"] = None
            data["rental_start_date"]   = ""
            data["rental_end_date"]     = ""
            # Combos don"t support pot add-ons
            if cid:
                data["selected_pot_id"] = None
            else:
                data["selected_pot_id"] = data.get("selected_pot_id") or None
 
        data["is_gift"] = bool(data.get("is_gift"))
        return data

class CartUpdateForm(forms.Form):
    item_id = forms.IntegerField(min_value=1)
    quantity = forms.IntegerField(min_value=0)

class CheckoutForm(forms.Form):
    selected_address = forms.IntegerField(required=False, widget=forms.HiddenInput())
    use_new_address  = forms.BooleanField(required=False, initial=False, widget=forms.HiddenInput())
 
    full_name    = forms.CharField(max_length=120, required=False)
    email        = forms.EmailField(required=False)
    phone        = forms.CharField(max_length=20, required=False)
    address_line = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False, label="Address")
    city         = forms.CharField(max_length=80, required=False)
    state        = forms.CharField(max_length=80, required=False, widget=forms.HiddenInput())
    pincode      = forms.CharField(max_length=10, required=False)
    delivery_state = forms.ModelChoiceField(
        queryset=active_delivery_state_queryset(),
        required=False,
        empty_label='Select state…',
        label='State',
    )
 
    payment = forms.ChoiceField(
        choices=[("cod", "Cash on Delivery"), ("razorpay", "Online Payment")],
        widget=forms.RadioSelect,
    )
    coupon_code = forms.CharField(
        max_length=40,
        required=False,
        widget=forms.HiddenInput(),
    )

    def __init__(self, *args, **kwargs):
        self.user        = kwargs.pop("user", None)
        self._cart_items = kwargs.pop("cart_items", None)
        self._cart       = kwargs.pop("cart", None)
        super().__init__(*args, **kwargs)
        self.fields["payment"].initial = "cod"
        configure_delivery_state_field(self.fields["delivery_state"], widget_class="form-control-bw")
        for field in self.fields.values():
            if isinstance(field.widget, (forms.RadioSelect, forms.HiddenInput)):
                continue
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} form-input".strip()

    def clean(self):
        try:
            cleaned_data     = super().clean()
            selected_address = cleaned_data.get("selected_address")
            use_new_address  = cleaned_data.get("use_new_address")
            is_guest         = not self.user
            delivery_on      = delivery_enabled()

            if is_guest and delivery_on:
                use_new_address = True
                cleaned_data["use_new_address"] = True
                selected_address = None

            if selected_address and (not use_new_address) and self.user:
                try:
                    address = Address.objects.get(pk=selected_address, user=self.user, is_snapshot=False)
                    cleaned_data["full_name"]    = address.full_name
                    cleaned_data["phone"]        = address.phone
                    cleaned_data["email"]        = address.email
                    cleaned_data["address_line"] = address.address_line
                    cleaned_data["city"]         = address.city
                    cleaned_data["pincode"]      = address.pincode
                    if address.delivery_state_id:
                        cleaned_data["delivery_state"] = address.delivery_state
                        cleaned_data["state"] = address.delivery_state.name
                    else:
                        cleaned_data["state"] = address.state
                        resolved_id = resolve_delivery_state_id(state_text=address.state)
                        if resolved_id:
                            from app.models import DeliveryState
                            cleaned_data["delivery_state"] = DeliveryState.objects.get(pk=resolved_id)
                            cleaned_data["state"] = cleaned_data["delivery_state"].name
                except Address.DoesNotExist:
                    raise forms.ValidationError("Selected address not found.")
                except Exception:
                    raise forms.ValidationError("Failed to retrieve address. Please try again.")
            else:
                if not use_new_address and not selected_address:
                    try:
                        if self.user and Address.objects.filter(user=self.user, is_snapshot=False).exists():
                            raise forms.ValidationError("Please select an address or add a new one.")
                        else:
                            use_new_address = True
                            cleaned_data["use_new_address"] = True
                    except forms.ValidationError:
                        raise
                    except Exception:
                        raise forms.ValidationError("Failed to retrieve addresses. Please try again.")

                if use_new_address and delivery_on:
                    required_fields = ["full_name", "phone", "address_line", "city", "delivery_state", "pincode"]
                    if is_guest:
                        required_fields = ["full_name", "email", "phone", "address_line", "city", "delivery_state", "pincode"]
                    for field in required_fields:
                        if not cleaned_data.get(field):
                            self.add_error(field, "This field is required.")
                    if cleaned_data.get("phone"):
                        self._validate_phone(cleaned_data.get("phone"))
                    if cleaned_data.get("pincode"):
                        self._validate_pincode_format(cleaned_data.get("pincode"))
                    sync_state_text_from_delivery_state(cleaned_data)

            state_id = resolve_delivery_state_id(
                delivery_state=cleaned_data.get("delivery_state"),
                state_text=cleaned_data.get("state", ""),
            )
            if self._cart_items is not None:
                if not state_id:
                    self.add_error("delivery_state", "Please select a valid delivery state.")
                else:
                    delivery_issues = get_cart_delivery_issues(self._cart_items, state_id)
                    if delivery_issues:
                        self.add_error("delivery_state", format_cart_delivery_error(delivery_issues))

            coupon_code = (cleaned_data.get("coupon_code") or "").strip()
            if coupon_code:
                from app.services.coupon_service import CouponError, validate_for_checkout
                from app.services.cart_order import CartService

                subtotal = 0
                if self._cart is not None:
                    subtotal = CartService.compute_totals(self._cart, state_id=None).subtotal
                elif self._cart_items is not None:
                    subtotal = sum((getattr(i, "line_total", 0) or 0) for i in self._cart_items)
                try:
                    validated = validate_for_checkout(
                        coupon_code,
                        subtotal=subtotal,
                        user=self.user,
                        email=cleaned_data.get("email") or "",
                        phone=cleaned_data.get("phone") or "",
                    )
                    cleaned_data["coupon_code"] = validated.code
                except CouponError as exc:
                    self.add_error("coupon_code", exc.message)

            return cleaned_data

        except forms.ValidationError:
            raise
        except Exception:
            raise forms.ValidationError("An error occurred. Please try again.")

    def _validate_phone(self, phone):
        if not phone:
            self.add_error("phone", "Phone number is required.")
            return
        phone   = phone.strip()
        cleaned = phone.replace("+91", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
        if not cleaned.isdigit():
            self.add_error("phone", "Phone number should contain only digits (and optional +91 prefix).")
            return
        if len(cleaned) != 10:
            self.add_error("phone", "Phone number must be exactly 10 digits.")
            return
        if cleaned[0] not in ["6", "7", "8", "9"]:
            self.add_error("phone", "Phone number should start with 6, 7, 8, or 9.")
 
    def _validate_pincode_format(self, pincode):
        if not pincode:
            self.add_error("pincode", "PIN code is required.")
            return
        cleaned = pincode.strip().replace("-", "").replace(" ", "")
        if not cleaned.isdigit():
            self.add_error("pincode", "PIN code should contain only digits.")
            return
        if len(cleaned) != 6:
            self.add_error("pincode", "PIN code must be exactly 6 digits.")
            return
        if cleaned[0] == "0":
            self.add_error("pincode", "PIN code cannot start with 0.")
 
    _validate_pincode = _validate_pincode_format

class ContactForm(forms.ModelForm):

    class Meta:
        model = ContactMessage
        fields = ["name", "email", "subject", "message"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} form-input".strip()

class NewsletterForm(forms.ModelForm):

    class Meta:
        model = NewsletterSubscription
        fields = ["email"]

class EmailOTPRequestForm(forms.Form):
    email = forms.EmailField(max_length=254, required=True, validators=[EmailValidator()], widget=forms.EmailInput(attrs={"class": "form-input", "placeholder": "Enter your email address", "autocomplete": "email", "autofocus": True}))

    def clean_email(self):
        email = self.cleaned_data.get("email", "").lower().strip()
        return email

class OTPVerificationForm(forms.Form):
    email = forms.EmailField(widget=forms.HiddenInput())
    otp = forms.CharField(max_length=4, min_length=4, required=True, validators=[RegexValidator(regex="^\\d{4}$", message="OTP must be exactly 4 digits")], widget=forms.TextInput(attrs={"class": "form-input otp-input", "placeholder": "0000", "maxlength": "4", "pattern": "[0-9]{4}", "inputmode": "numeric", "autocomplete": "one-time-code"}))

    def clean_otp(self):
        otp = self.cleaned_data.get("otp", "").strip()
        if not otp.isdigit():
            raise forms.ValidationError("OTP must contain only digits")
        return otp

class UserProfileForm(forms.Form):
    first_name = forms.CharField(max_length=30, required=False, widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "First Name"}))
    last_name = forms.CharField(max_length=30, required=False, widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "Last Name"}))
    phone = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "Phone Number (10 digits)", "inputmode": "tel", "pattern": "[0-9+\\s\\-()]*", "data-only-numbers": "true", "autocomplete": "tel"}))

    def clean_phone(self):
        phone = self.cleaned_data.get("phone", "").strip()
        if not phone:
            return phone
        cleaned_phone = phone.replace("+91", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
        if not cleaned_phone.isdigit():
            raise forms.ValidationError("Phone number should contain only digits (and optional +91 prefix).")
        if len(cleaned_phone) != 10:
            raise forms.ValidationError("Phone number must be exactly 10 digits.")
        if cleaned_phone[0] not in ["6", "7", "8", "9"]:
            raise forms.ValidationError("Phone number should start with 6, 7, 8, or 9.")
        return phone

class AddressForm(forms.ModelForm):

    class Meta:
        model = Address
        fields = ["full_name", "phone", "address_line", "city", "delivery_state", "pincode", "is_default"]
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "form-input", "placeholder": "Full Name"}),
            "phone": forms.TextInput(attrs={"class": "form-input", "placeholder": "Phone Number (10 digits)", "inputmode": "tel", "pattern": "[0-9+\\s\\-()]*", "maxlength": "15", "data-only-numbers": "true", "autocomplete": "tel"}),
            "address_line": forms.Textarea(attrs={"class": "form-input", "placeholder": "Street Address", "rows": 3}),
            "city": forms.TextInput(attrs={"class": "form-input", "placeholder": "City"}),
            "delivery_state": forms.Select(attrs={"class": "form-input"}),
            "pincode": forms.TextInput(attrs={"class": "form-input", "placeholder": "PIN Code (6 digits)", "inputmode": "numeric", "pattern": "[0-9\\s\\-]*", "maxlength": "8", "data-only-numbers": "true"}),
            "is_default": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configure_delivery_state_field(self.fields["delivery_state"])
        self.fields["delivery_state"].required = True

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.delivery_state_id:
            instance.state = instance.delivery_state.name
        if commit:
            instance.save()
        return instance

    def clean_phone(self):
        phone = self.cleaned_data.get("phone", "").strip()
        if not phone:
            raise forms.ValidationError("Phone number is required.")
        cleaned_phone = phone.replace("+91", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
        if not cleaned_phone.isdigit():
            raise forms.ValidationError("Phone number should contain only digits (and optional +91 prefix).")
        if len(cleaned_phone) != 10:
            raise forms.ValidationError("Phone number must be exactly 10 digits.")
        if cleaned_phone[0] not in ["6", "7", "8", "9"]:
            raise forms.ValidationError("Phone number should start with 6, 7, 8, or 9.")
        return phone

    def clean_pincode(self):
        pincode = self.cleaned_data.get("pincode", "").strip()
        if not pincode:
            raise forms.ValidationError("PIN code is required.")
        cleaned_pincode = pincode.replace("-", "").replace(" ", "")
        if not cleaned_pincode.isdigit():
            raise forms.ValidationError("PIN code should contain only digits.")
        if len(cleaned_pincode) != 6:
            raise forms.ValidationError("PIN code must be exactly 6 digits.")
        if cleaned_pincode[0] == "0":
            raise forms.ValidationError("PIN code cannot start with 0.")
        return pincode

class ReviewForm(forms.ModelForm):

    class Meta:
        model = Review
        fields = ["rating", "title", "comment"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["rating"].widget = forms.RadioSelect(choices=[(i, f"{i} Star" if i == 1 else f"{i} Stars") for i in range(1, 6)])
        self.fields["title"].required = False
        self.fields["comment"].required = False
        for name, field in self.fields.items():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} form-input".strip()

    def clean_rating(self):
        rating = self.cleaned_data.get("rating")
        if rating is None:
            raise forms.ValidationError("Please select a rating.")
        try:
            rating_int = int(rating)
        except (TypeError, ValueError):
            raise forms.ValidationError("Invalid rating value.")
        if rating_int < 1 or rating_int > 5:
            raise forms.ValidationError("Rating must be between 1 and 5 stars.")
        return rating_int
