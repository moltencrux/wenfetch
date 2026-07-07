from hanzidentifier import identify, TRADITIONAL, SIMPLIFIED, BOTH, MIXED, UNKNOWN
import opencc

t2s = opencc.OpenCC('t2s')
s2t = opencc.OpenCC('s2t')


def get_vocab_display(entry, preference: str = "simplified", swap: bool = False):
    """
    Returns display data for a VocabEntry.
    """
    original = entry.word
    simp = t2s.convert(original)
    trad = s2t.convert(original)
    has_variant = simp != trad

    use_trad_first = (preference == "traditional") != swap

    if use_trad_first:
        primary = trad
        secondary = simp if has_variant else None
    else:
        primary = simp
        secondary = trad if has_variant else None

    return {
        'primary': primary,
        'secondary': secondary,
        'original': original,
        'has_variant': has_variant,
    }

def process_vocab_entry_on_add(original: str):
    """
    Process a word when user adds it.
    Returns (stored_word, normalized_for_matching)
    - stored_word: saved in VocabEntry.word (preserve user's original)
    - normalized_for_matching: simplified version for deduplication & matching
    """
    if not original:
        return original

    script_type = identify(original)

    if script_type == TRADITIONAL:
        return original

    elif script_type == SIMPLIFIED:
        # Simplified-only
        normalized = s2t.convert(original)
        # Round trip: Simp -> Trad -> Simp
        round_trip = t2s.convert(normalized)
        
        if round_trip != original:
            # Meaningful simplified variant
            return original
        else:
            return normalized

    elif script_type in (BOTH, MIXED):
        # Conversion may not be necessary in many cases, but there might be some
        # like 那里 that identify as BOTH but are simplified in reality
        normalized = s2t.convert(original)
        return normalized

    elif script_type == UNKNOWN:
        return original