import tempfile

import cups
import requests
from django import forms
from django.conf import settings
from django.contrib import messages
from django.http import HttpRequest
from django.http import HttpResponse
from django.shortcuts import redirect
from django.shortcuts import render
from ocflib.printing.quota import get_connection as get_quota_connection
from ocflib.printing.quota import get_quota

from ocfweb.auth import login_required
from ocfweb.component.forms import Form
from ocfweb.component.session import logged_in_user
from ocfweb.printing import get_printers


class WebPrintForm(Form):
    printer = forms.ChoiceField(
        label='Select Printer',
    )
    file = forms.FileField(
        label='File to Print',
    )
    otp = forms.CharField(
        label='Verification Code (From front of room)',
        min_length=6,
        max_length=6,
        widget=forms.TextInput(attrs={'placeholder': '123456'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        printers = get_printers()

        choices = []
        for name, info in printers.items():
            if info.get('printer-is-shared', True):
                choices.append((name, info.get('printer-info', name)))

        if not choices:
            choices = [('', 'No printers available')]

        self.fields['printer'].choices = choices

    def clean_file(self):
        return self.cleaned_data.get('file')

    def clean_otp(self):
        otp = self.cleaned_data.get('otp')
        if not otp:
            return otp

        verify_url = f"{settings.PRINTING_OTP_URL}/verify/{otp}"
        try:
            response = requests.get(verify_url, timeout=5)
            response.raise_for_status()
            data = response.json()
            if not data.get('valid'):
                raise forms.ValidationError('Invalid code. Please get the code from the front of the room to enter.')
        except (requests.RequestException, ValueError):
            # Fail closed on server error
            raise forms.ValidationError('Could not verify code with server. Please try again later.')

        return otp


@login_required
def web_print(request: HttpRequest) -> HttpResponse:
    user = logged_in_user(request)

    with get_quota_connection() as c:
        quota = get_quota(c, user)

    if request.method == 'POST':
        form = WebPrintForm(request.POST, request.FILES)
        if form.is_valid():
            printer = form.cleaned_data['printer']
            uploaded_file = form.cleaned_data['file']

            try:
                with tempfile.NamedTemporaryFile() as tmp:
                    for chunk in uploaded_file.chunks():
                        tmp.write(chunk)
                    tmp.flush()

                    # Submit to printhost CUPS
                    cups.setUser(user)
                    conn = cups.Connection(host='printhost')
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
                    return redirect('web_print')
            except Exception as e:
                messages.error(request, f"Failed to print: {e}")
    else:
        form = WebPrintForm()

    return render(
        request,
        'account/print.html',
        {
            'title': 'Web Printing',
            'form': form,
            'quota': quota,
        },
    )
