"""
Django template filters for converting between Traditional and Simplified
Chinese using OpenCC.

Setup:
    1. pip install opencc
       (if that fails to build on your platform, use the pure-Python
       fallback instead: pip install opencc-python-reimplemented --
       the import and API are the same)

    2. Put this file at:
       <your_app>/templatetags/opencc_filters.py
       (create an empty __init__.py in templatetags/ if it's not there yet)

    3. In your template:
       {% load opencc_filters %}
       {{ some_text|s2t }}          simplified -> traditional
       {{ some_text|t2s }}          traditional -> simplified
       {{ some_text|s2tw }}         simplified -> traditional (Taiwan)
       {{ some_text|tw2s }}         traditional (Taiwan) -> simplified
       {{ some_text|s2hk }}         simplified -> traditional (Hong Kong)
       {{ some_text|hk2s }}         traditional (Hong Kong) -> simplified
       {{ some_text|opencc_convert:"s2twp" }}   any config, generic filter
"""
from django import template
import opencc

register = template.Library()

# OpenCC converters are cheap-ish to build but there's no reason to
# rebuild one per call, so cache them by config name.
_converters = {}


def _get_converter(config):
    converter = _converters.get(config)
    if converter is None:
        converter = opencc.OpenCC(config)
        _converters[config] = converter
    return converter


def _convert(value, config):
    if value is None:
        return value
    return _get_converter(config).convert(str(value))


@register.filter(name="s2t")
def simplified_to_traditional(value):
    """Simplified Chinese -> Traditional Chinese"""
    return _convert(value, "s2t")


@register.filter(name="t2s")
def traditional_to_simplified(value):
    """Traditional Chinese -> Simplified Chinese"""
    return _convert(value, "t2s")


@register.filter(name="s2tw")
def simplified_to_traditional_tw(value):
    """Simplified Chinese -> Traditional Chinese (Taiwan standard)"""
    return _convert(value, "s2tw")


@register.filter(name="tw2s")
def traditional_tw_to_simplified(value):
    """Traditional Chinese (Taiwan standard) -> Simplified Chinese"""
    return _convert(value, "tw2s")


@register.filter(name="s2hk")
def simplified_to_traditional_hk(value):
    """Simplified Chinese -> Traditional Chinese (Hong Kong standard)"""
    return _convert(value, "s2hk")


@register.filter(name="hk2s")
def traditional_hk_to_simplified(value):
    """Traditional Chinese (Hong Kong standard) -> Simplified Chinese"""
    return _convert(value, "hk2s")


@register.filter(name="opencc_convert")
def opencc_convert(value, config="s2t"):
    """
    Generic filter, in case you want a less common config
    (e.g. s2twp, tw2sp, t2tw, t2hk, t2jp, jp2t) without adding a
    dedicated filter for it:

        {{ text|opencc_convert:"s2twp" }}
    """
    return _convert(value, config)


# ---------------------------------------------------------------------
# Preference-driven conversion
#
# A preference names the *target* script the reader wants, not the
# source script of the stored text. This works cleanly because OpenCC
# configs are one-directional and idempotent on text that's already in
# the target script (e.g. running "s2t" on text that's already
# Traditional just leaves it unchanged), so you don't need to know or
# detect what the underlying text currently is.
# ---------------------------------------------------------------------

PREFERENCE_CONFIGS = {
    "traditional": "s2t",
    "trad": "s2t",
    "traditional_tw": "s2tw",
    "trad_tw": "s2tw",
    "traditional_hk": "s2hk",
    "trad_hk": "s2hk",
    "simplified": "t2s",
    "simp": "t2s",
}

DEFAULT_PREFERENCE = "traditional"


def _config_for_preference(preference):
    return PREFERENCE_CONFIGS.get(
        preference, PREFERENCE_CONFIGS[DEFAULT_PREFERENCE]
    )


@register.filter(name="zhconv")
def zhconv(value, preference=None):
    """
    Filter version: pass the preference in explicitly as the filter
    argument. Since filter arguments are resolved from the template
    context automatically, this is what "context aware" looks like
    for a filter -- you're just pointing it at a context variable:

        {{ text|zhconv:zh_pref }}
        {{ text|zhconv:request.user.profile.zh_pref }}
        {{ text|zhconv:"trad_tw" }}

    Unrecognized or missing preferences fall back to
    DEFAULT_PREFERENCE rather than raising, so a bad/absent value
    degrades gracefully instead of breaking the page.
    """
    return _convert(value, _config_for_preference(preference))


@register.simple_tag(takes_context=True, name="zhconv_ctx")
def zhconv_ctx(context, value):
    """
    Tag version: reads the preference straight out of the render
    context (key "zh_pref") instead of requiring it as an explicit
    argument at every call site:

        {% load opencc_filters %}
        {% zhconv_ctx some_text %}

    This has to be a {% %} tag rather than a |filter, because Django
    never gives filters access to the full context -- only tags get
    that. Pair it with a context processor (see
    zh_pref_context_processor.py) so "zh_pref" is set once per
    request and every template just works without passing anything.
    """
    preference = context.get("zh_pref", DEFAULT_PREFERENCE)
    return _convert(value, _config_for_preference(preference))


# Reverse config per preference, used by zhconv_ctx_opposite. Deliberately
# not just "look up the opposite preference and reuse _config_for_preference",
# because that would lose regional flavor -- e.g. the true reverse of
# Taiwan-flavored Traditional is "tw2s" (which also converts Taiwan-specific
# vocabulary back to Mainland-standard wording), not the generic "t2s".
OPPOSITE_CONFIGS = {
    "traditional": "t2s",
    "trad": "t2s",
    "traditional_tw": "tw2s",
    "trad_tw": "tw2s",
    "traditional_hk": "hk2s",
    "trad_hk": "hk2s",
    "simplified": "s2t",
    "simp": "s2t",
}


def _opposite_config_for_preference(preference):
    return OPPOSITE_CONFIGS.get(
        preference, OPPOSITE_CONFIGS[DEFAULT_PREFERENCE]
    )


@register.simple_tag(takes_context=True, name="zhconv_ctx_opposite")
def zhconv_ctx_opposite(context, value):
    """
    Complement of zhconv_ctx: renders `value` in whichever script is
    NOT the current zh_pref -- useful for an "also show me the other
    script" toggle/link next to the main text:

        {% load opencc_filters %}
        {% zhconv_ctx some_text %}
        (<a href="?zh_pref=toggle">{% zhconv_ctx_opposite some_text %}</a>)

    Uses OPPOSITE_CONFIGS rather than just negating the preference and
    re-running _config_for_preference, so regional variants (Taiwan,
    Hong Kong) reverse correctly using their matching tw2s/hk2s
    configs instead of the generic t2s.
    """
    preference = context.get("zh_pref", DEFAULT_PREFERENCE)
    return _convert(value, _opposite_config_for_preference(preference))


@register.simple_tag(takes_context=True, name="zhconv_dual")
def zhconv_dual(context, value, separator=" / "):
    """
    Renders both the preferred and opposite script, but collapses to a
    single copy when they come out identical (common for short strings,
    proper nouns, numbers, or any text made up entirely of characters
    that don't differ between Simplified and Traditional):

        {% load opencc_filters %}
        {% zhconv_dual some_text %}
        {% zhconv_dual some_text separator=" (" %}

    Note: this calls the same underlying functions as zhconv_ctx and
    zhconv_ctx_opposite directly (they're plain functions under their
    @register.simple_tag decorators, so they're reusable here without
    going through template tag dispatch).
    """
    preferred = zhconv_ctx(context, value)
    opposite = zhconv_ctx_opposite(context, value)

    if preferred == opposite:
        return preferred

    return f"{preferred}{separator}{opposite}"
