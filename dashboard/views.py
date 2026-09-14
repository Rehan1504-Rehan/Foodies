"""Dashboard entry point: send each role to their own interface."""

from django.shortcuts import redirect

from accounts.permissions import home_url_for


def dashboard_redirect(request):
    """Single post-login landing that respects the user's role."""
    if not request.user.is_authenticated:
        return redirect("accounts:login")
    return redirect(home_url_for(request.user))
