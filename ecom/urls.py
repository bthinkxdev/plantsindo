from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
urlpatterns = [path('admin/', admin.site.urls), path('dashboard/', include('app.admin_urls')), path('accounts/', include('app.auth_urls')), path('', include('app.urls'))]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
handler400 = 'app.error_handlers.error_400'
handler403 = 'app.error_handlers.error_403'
handler404 = 'app.error_handlers.error_404'
handler500 = 'app.error_handlers.error_500'
