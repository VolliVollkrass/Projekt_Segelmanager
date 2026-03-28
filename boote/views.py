from django.shortcuts import render, get_object_or_404, redirect
from .models import Boot
from .forms import BootForm, KabineFormSet
from toern.models import Toern
from django.contrib.auth.decorators import login_required
from utils.permissions import anbieter_required
from django.core.exceptions import PermissionDenied


def is_owner_or_admin(user, obj):
    return user == obj.toern.anbieter or user.is_superuser


# =========================
# CREATE
# =========================
@login_required
@anbieter_required
def boot_create(request, toern_id):
    toern = get_object_or_404(Toern, id=toern_id)

    if request.user != toern.anbieter and not request.user.is_superuser:
        raise PermissionDenied

    if request.method == "POST":
        form = BootForm(request.POST, request.FILES)
        formset = KabineFormSet(request.POST, prefix="kabine_set")

        if form.is_valid() and formset.is_valid():
            boot = form.save(commit=False)
            boot.toern = toern
            boot.save()

            # 🔥 WICHTIG: instance setzen NACH save
            formset.instance = boot
            formset.save()

            return redirect("toern_detail", pk=toern.id)

    else:
        form = BootForm()
        formset = KabineFormSet(prefix="kabine_set")

    return render(request, "boote/boot_form.html", {
        "form": form,
        "formset": formset,
        "toern": toern
    })


# =========================
# UPDATE
# =========================
@login_required
@anbieter_required
def boot_update(request, pk):
    boot = get_object_or_404(Boot, pk=pk)

    if request.user != boot.toern.anbieter and not request.user.is_superuser:
        raise PermissionDenied

    if request.method == "POST":
        form = BootForm(request.POST, request.FILES, instance=boot)
        formset = KabineFormSet(request.POST, instance=boot, prefix="kabine_set")

        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()

            return redirect("toern_detail", pk=boot.toern.id)

    else:
        form = BootForm(instance=boot)
        formset = KabineFormSet(instance=boot, prefix="kabine_set")

    return render(request, "boote/boot_form.html", {
        "form": form,
        "formset": formset,
        "boot": boot
    })