from django.views.generic import ListView, DetailView
from app.models.cms import BlogPost

class BlogListView(ListView):
    model = BlogPost
    template_name = 'pages/blog_list.html'
    context_object_name = 'posts'
    paginate_by = 12

    def get_queryset(self):
        return BlogPost.objects.filter(is_published=True).order_by('-published_at', '-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_page'] = 'blog'
        return context

class BlogDetailView(DetailView):
    model = BlogPost
    template_name = 'pages/blog_detail.html'
    context_object_name = 'post'

    def get_queryset(self):
        return BlogPost.objects.filter(is_published=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_page'] = 'blog'
        return context
