"""
Context processors for accounts app
"""
from .utils import resolve_active_branch


def branch_context(request):
    """
    Add branch context to all templates for directors.
    Makes active_branch, all_branches, and branch_selected available in templates.
    """
    if request.user.is_authenticated and request.user.is_director():
        active_branch, all_branches, is_selected = resolve_active_branch(request)
        return {
            'active_branch': active_branch,
            'all_branches': all_branches,
            'branch_selected': is_selected,
            'has_multiple_branches': len(all_branches) > 1,
        }
    return {
        'active_branch': None,
        'all_branches': [],
        'branch_selected': False,
        'has_multiple_branches': False,
    }

