import tempfile

import cups
from django import forms
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from ocflib.printing.quota import get_connection as get_quota_connection
from ocflib.printing.quota import get_quota

from ocfweb.auth import login_required
from ocfweb.component.forms import Form
from ocfweb.component.session import logged_in_user
from ocfweb.printing import get_printers


class WebPrintForm(Form):
    printer = forms.ChoiceField(
        label="Select Printer",
    )
    file = forms.FileField(
        label="File to Print",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        printers = get_printers()

        choices = []
        for name, info in printers.items():
            if info.get("printer-is-shared", True):
                choices.append((name, info.get("printer-info", name)))

        if not choices:
            choices = [("", "No printers available")]

        self.fields["printer"].choices = choices

    def clean_file(self):
        return self.cleaned_data.get("file")


@login_required
def web_print(request: HttpRequest) -> HttpResponse:
    user = logged_in_user(request)

    with get_quota_connection() as c:
        quota = get_quota(c, user)

    if request.method == "POST":
        form = WebPrintForm(request.POST, request.FILES)
        if form.is_valid():
            printer = form.cleaned_data["printer"]
            uploaded_file = form.cleaned_data["file"]

            try:
                with tempfile.NamedTemporaryFile() as tmp:
                    for chunk in uploaded_file.chunks():
                        tmp.write(chunk)
                    tmp.flush()

                    # Submit to printhost CUPS
                    cups.setUser(user)
                    conn = cups.Connection(host="printhost")
                    conn.printFile(
                        printer,
                        tmp.name,
                        uploaded_file.name,
                        {},
                    )

                    messages.success(
                        request,
                        f'Successfully submitted "{uploaded_file.name}" to {printer}.',
                    )
                    return redirect("web_print")
            except Exception as e:
                messages.error(request, f"Failed to print: {e}")
    else:
        form = WebPrintForm()

    return render(
        request,
        "account/print.html",
        {
            "title": "Web Printing",
            "form": form,
            "quota": quota,
        },
    )
