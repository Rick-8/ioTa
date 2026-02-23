from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import NewsStoryForm
from .models import NewsStory


def _is_superuser(user):
    return user.is_authenticated and user.is_superuser


def news_list(request):
    is_admin = _is_superuser(request.user)

    # Breaking should only ever come from non-archived stories
    breaking = NewsStory.objects.filter(is_breaking=True, is_archived=False).first()

    # Superusers see all stories, everyone else only non-archived
    stories_qs = NewsStory.objects.all() if is_admin else NewsStory.objects.filter(is_archived=False)
    stories = stories_qs.order_by("-created_at")

    # Keep breaking out of the main list (it appears in the feature block)
    if breaking:
        stories = stories.exclude(pk=breaking.pk)

    create_form = NewsStoryForm() if is_admin else None

    context = {
        "breaking": breaking,
        "stories": stories,
        "create_form": create_form,
    }
    return render(request, "news/news_list.html", context)


@login_required
@user_passes_test(_is_superuser)
def news_create(request):
    if request.method != "POST":
        raise Http404()

    form = NewsStoryForm(request.POST, request.FILES)
    if form.is_valid():
        story = form.save()
        messages.success(request, "Story created.")
        return redirect("news_detail", slug=story.slug)

    # If invalid, re-render the list with the same visibility rules as admins:
    breaking = NewsStory.objects.filter(is_breaking=True, is_archived=False).first()
    stories = NewsStory.objects.all().order_by("-created_at")
    if breaking:
        stories = stories.exclude(pk=breaking.pk)

    return render(
        request,
        "news/news_list.html",
        {"breaking": breaking, "stories": stories, "create_form": form},
        status=400,
    )


def news_detail(request, slug):
    story = get_object_or_404(NewsStory, slug=slug)
    edit_form = NewsStoryForm(instance=story) if _is_superuser(request.user) else None

    return render(
        request,
        "news/news_detail.html",
        {"story": story, "edit_form": edit_form},
    )


@login_required
@user_passes_test(_is_superuser)
def news_edit(request, slug):
    story = get_object_or_404(NewsStory, slug=slug)
    if request.method != "POST":
        raise Http404()

    form = NewsStoryForm(request.POST, request.FILES, instance=story)
    if form.is_valid():
        form.save()
        messages.success(request, "Story updated.")
        return redirect("news_detail", slug=story.slug)

    return render(
        request,
        "news/news_detail.html",
        {"story": story, "edit_form": form},
        status=400,
    )


@login_required
@user_passes_test(_is_superuser)
@require_POST
def news_delete(request, slug):
    story = get_object_or_404(NewsStory, slug=slug)
    story.delete()
    messages.success(request, "Story deleted.")
    return redirect("news_list")


@login_required
@user_passes_test(_is_superuser)
@require_POST
def news_toggle_archive(request, slug):
    story = get_object_or_404(NewsStory, slug=slug)
    story.is_archived = not story.is_archived
    if story.is_archived:
        story.is_breaking = False
    story.save()
    messages.success(request, "Archive status updated.")
    return redirect(request.POST.get("next") or "news_detail", slug=story.slug)


@login_required
@user_passes_test(_is_superuser)
@require_POST
def news_set_breaking(request, slug):
    story = get_object_or_404(NewsStory, slug=slug)

    if story.is_archived:
        messages.error(request, "Archived stories cannot be set as Breaking.")
        return redirect(request.POST.get("next") or "news_detail", slug=story.slug)

    NewsStory.set_breaking(story.id)
    messages.success(request, "Breaking story updated.")
    return redirect(request.POST.get("next") or "news_list")