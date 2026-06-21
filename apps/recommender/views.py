from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages

from .models import VocabList, VocabEntry
from .services import enrich_with_metadata, get_sources, import_vocab, recommend


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

@login_required
def recommend_view(request):
    vocab_lists = VocabList.objects.filter(user=request.user)
    sources = get_sources()
    results = []
    selected_list_id = None
    selected_source = None
    heuristic = "avg"

    if request.method == "POST":
        selected_list_id = request.POST.get("vocab_list")
        selected_source = request.POST.get("source") or None
        heuristic = request.POST.get("heuristic", "avg")
        n = int(request.POST.get("n", 10))

        if selected_list_id:
            vocab_list = get_object_or_404(
                VocabList, id=selected_list_id, user=request.user
            )
            results = recommend(vocab_list, source=selected_source,
                                heuristic=heuristic, n=n)
            results = enrich_with_metadata(results)

    return render(request, "recommender/recommend.html", {
        "vocab_lists": vocab_lists,
        "sources": sources,
        "results": results,
        "selected_list_id": selected_list_id,
        "selected_source": selected_source,
        "heuristic": heuristic,
    })


# ---------------------------------------------------------------------------
# Vocab list management
# ---------------------------------------------------------------------------

@login_required
def vocab_list_index(request):
    """List all vocab lists for the current user."""
    vocab_lists = VocabList.objects.filter(user=request.user)
    return render(request, "recommender/vocab_list_index.html", {
        "vocab_lists": vocab_lists,
    })


@login_required
def vocab_list_create(request):
    """Create a new vocab list."""
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if name:
            vocab_list, created = VocabList.objects.get_or_create(
                user=request.user, name=name
            )
            if created:
                messages.success(request, f'Created vocab list "{name}".')
            else:
                messages.info(request, f'Vocab list "{name}" already exists.')
            return redirect("vocab_list_detail", pk=vocab_list.pk)
    return render(request, "recommender/vocab_list_create.html")


@login_required
def vocab_list_detail(request, pk):
    """View a vocab list and import new words."""
    vocab_list = get_object_or_404(VocabList, pk=pk, user=request.user)
    entries = vocab_list.entries.order_by("word")
    added = skipped = 0

    if request.method == "POST":
        text = ""
        if "vocab_file" in request.FILES:
            uploaded = request.FILES["vocab_file"]
            text = uploaded.read().decode("utf-8", errors="replace")
        elif "vocab_text" in request.POST:
            text = request.POST["vocab_text"]

        if text:
            added, skipped = import_vocab(vocab_list, text)
            messages.success(
                request,
                f"Added {added} words ({skipped} already in list)."
            )
            return redirect("vocab_list_detail", pk=pk)

    return render(request, "recommender/vocab_list_detail.html", {
        "vocab_list": vocab_list,
        "entries": entries,
        "entry_count": entries.count(),
    })


@login_required
def vocab_list_delete(request, pk):
    """Delete a vocab list."""
    vocab_list = get_object_or_404(VocabList, pk=pk, user=request.user)
    if request.method == "POST":
        name = vocab_list.name
        vocab_list.delete()
        messages.success(request, f'Deleted vocab list "{name}".')
        return redirect("vocab_list_index")
    return render(request, "recommender/vocab_list_confirm_delete.html", {
        "vocab_list": vocab_list,
    })
