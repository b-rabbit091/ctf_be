from django.utils.text import slugify

def generate_unique_slug(model_class, title):
    base_slug = slugify(title)
    slug = base_slug
    count = 1
    while model_class.objects.filter(slug=slug).exists():
        slug = f"{base_slug}-{count}"
        count += 1
    return slug
