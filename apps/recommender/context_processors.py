"""
Optional context processor that makes a "zh_pref" variable available in
every template's context automatically, so you don't have to pass it
into render() manually in every view.

Setup:
    1. Put this file in one of your apps, e.g. myapp/context_processors.py
    2. In settings.py, add it to TEMPLATES:

        TEMPLATES = [
            {
                ...
                'OPTIONS': {
                    'context_processors': [
                        ...
                        'myapp.context_processors.zh_pref',
                    ],
                },
            },
        ]

    3. Now every template automatically has `zh_pref` in context, usable
       directly with the zhconv_ctx tag:

        {% load opencc_filters %}
        {% zhconv_ctx some_text %}

       or with the zhconv filter:

        {{ some_text|zhconv:zh_pref }}

Adjust the lookup logic below to match wherever you actually store the
user's preference (session, user profile field, query param, an
Accept-Language-derived guess, etc).

Resolution order:
    1. explicit session override (e.g. user picked it from a UI toggle)
    2. saved user profile preference
    3. hint from the active interface language (i18n's LANGUAGE_CODE)
    4. hardcoded default
"""

from django.utils.translation import get_language

# Map interface language codes to a zh_pref value. Adjust the keys to
# match whatever codes actually show up in your LANGUAGE_CODE / i18n
# setup (e.g. check LANGUAGES in settings.py) -- Django will give you
# things like "zh-hans" / "zh-hant" if you're using those, or
# "zh-cn" / "zh-tw" / "zh-hk" if you defined your own custom codes.
LANGUAGE_TO_ZH_PREF = {
    "zh-hans": "simplified",
    "zh-cn": "simplified",
    "zh-hant": "traditional",
    "zh-tw": "trad_tw",
    "zh-hk": "trad_hk",
}

DEFAULT_ZH_PREF = "traditional"


def zh_pref(request):
    preference = request.session.get("zh_pref")

    if not preference and getattr(request, "user", None) and request.user.is_authenticated:
        profile = getattr(request.user, "profile", None)
        preference = getattr(profile, "preferred_script", None)

    if not preference:
        preference = LANGUAGE_TO_ZH_PREF.get(get_language())

    return {"zh_pref": preference or DEFAULT_ZH_PREF}
