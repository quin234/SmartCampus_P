"""
Utility functions for accounts app, including branch resolution for directors
"""
from django.contrib import messages
from education.models import College


def resolve_active_branch(request):
    """
    Resolve the active branch for the current request.
    
    Resolution order:
    1. User-selected branch (from GET parameter or session)
    2. Default branch assigned to the director (if only one branch exists)
    3. Main college (fallback)
    
    Returns:
        tuple: (active_branch, all_available_branches, is_branch_selected)
    """
    if not request.user.is_authenticated or not request.user.is_director():
        # For non-directors, return their college
        if hasattr(request.user, 'college') and request.user.college:
            return request.user.college, [request.user.college], False
        return None, [], False
    
    main_college = request.user.college
    if not main_college:
        return None, [], False
    
    # Get all available branches (main + branches)
    all_branches = [main_college]
    if main_college.is_main_college():
        all_branches.extend(main_college.get_all_branches())
    
    # Resolution order:
    # 1. Check GET parameter (branch_id)
    branch_id = request.GET.get('branch_id')
    if branch_id:
        try:
            selected_branch = College.objects.get(id=branch_id)
            # Verify it's a valid branch for this director
            if selected_branch in all_branches:
                # Store in session for persistence
                request.session['selected_branch_id'] = branch_id
                return selected_branch, all_branches, True
        except College.DoesNotExist:
            pass
    
    # 2. Check session for previously selected branch
    session_branch_id = request.session.get('selected_branch_id')
    if session_branch_id:
        try:
            selected_branch = College.objects.get(id=session_branch_id)
            if selected_branch in all_branches:
                return selected_branch, all_branches, True
        except College.DoesNotExist:
            # Clear invalid session value
            request.session.pop('selected_branch_id', None)
    
    # 3. Auto-select if only one branch exists (main college only)
    if len(all_branches) == 1:
        return main_college, all_branches, False
    
    # 4. Default to main college (but require selection if multiple branches exist)
    return main_college, all_branches, False


def validate_branch_selection(request, require_branch=True):
    """
    Validate that a branch is selected when required.
    
    Args:
        request: Django request object
        require_branch: If True, require branch selection when multiple branches exist
    
    Returns:
        tuple: (is_valid, active_branch, error_message)
    """
    active_branch, all_branches, is_selected = resolve_active_branch(request)
    
    if not active_branch:
        return False, None, "No college found for this user."
    
    # If multiple branches exist and branch selection is required but not selected
    if require_branch and len(all_branches) > 1 and not is_selected:
        return False, active_branch, "Please select a branch to view data."
    
    return True, active_branch, None


def get_colleges_to_query(request):
    """
    Get the list of colleges to query based on active branch.
    For directors, this returns [active_branch].
    For others, returns [their_college].
    
    Returns:
        list: List of College objects to query
    """
    active_branch, _, _ = resolve_active_branch(request)
    if active_branch:
        return [active_branch]
    return []

