"""Streamlit entry for the PCOS Food Scanner prototype."""

from dotenv import load_dotenv
import os
import streamlit as st

from core import db
from core.openfoodfacts import fetch_product
from core.vision import extract_product_from_label
from core.personalize import personalize
from core.profile import PCOS_TYPES, SYMPTOM_FIELDS, Profile
from core.scoring import score_food

try:
    from core.barcode import decode_barcode
except ImportError:
    decode_barcode = None

load_dotenv()

def _rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()


def _profile_form(existing=None):
    existing = existing or Profile()
    type_options = ["insulin_resistant", "inflammatory", "adrenal", "post_pill", "unknown"]
    labels = {
        "insulin_resistance": "Insulin resistance",
        "irregular_periods": "Irregular periods",
        "acne_or_hair": "Acne or hair symptoms",
        "inflammation_bloating": "Inflammation or bloating",
        "cravings": "Cravings",
        "weight_loss_goal": "Weight-loss goal",
    }
    with st.form("profile_form"):
        pcos_type = st.radio(
            "PCOS type",
            type_options,
            index=type_options.index(existing.pcos_type if existing.pcos_type in PCOS_TYPES else "unknown"),
        )
        values = {}
        for field in SYMPTOM_FIELDS:
            values[field] = st.checkbox(labels[field], value=getattr(existing, field))
        dietary_prefs = st.text_area("Dietary preferences", value=existing.dietary_prefs)
        submitted = st.form_submit_button("Save profile")
    if submitted:
        db.save_profile(Profile(pcos_type=pcos_type, dietary_prefs=dietary_prefs, **values))
        st.success("Profile saved.")
        _rerun()


def _read_label_product():
    st.warning("Not in Open Food Facts. Snap the nutrition label to score it.")
    label_image = st.camera_input("Nutrition label photo", key="nutrition_label_photo")
    if label_image is None:
        return None
    with st.spinner("Reading label..."):
        product = extract_product_from_label(label_image.getvalue())
    if product is None:
        st.error("Could not read the label.")
    return product


def _scan_tab(profile):
    image = None
    if decode_barcode is not None:
        image = st.camera_input("Scan barcode (or type below)")
    with st.form("scan_form"):
        barcode = st.text_input("Barcode")
        submitted = st.form_submit_button("Scan")
    fallback_active = st.session_state.get("label_fallback_active", False)
    if not submitted and image is None and not fallback_active:
        return

    product = None
    barcode = barcode.strip()
    if fallback_active and not submitted and image is None:
        product = _read_label_product()
        if product is None:
            return
        st.session_state.pop("label_fallback_active", None)

    if product is None:
        if not barcode:
            if image is not None:
                barcode = decode_barcode(image.getvalue())
                if barcode is None:
                    st.warning("Could not read barcode — try again or type it.")
                    return
            else:
                st.warning("Enter a barcode.")
                return

        try:
            product = fetch_product(barcode)
        except Exception as exc:
            st.error(f"Could not fetch product: {exc}")
            return
        if product is None:
            st.session_state["label_fallback_active"] = True
            product = _read_label_product()
            if product is None:
                return
            st.session_state.pop("label_fallback_active", None)

    scoring = score_food(product.get("nutriments_100g") or {}, product.get("nova_group"))
    guidance = personalize(scoring["score"], scoring["breakdown"], product, profile)

    st.subheader(product.get("name") or barcode)
    if product.get("brands"):
        st.write(product["brands"])
    st.metric("Score", guidance["adjusted_score"])
    st.write(f"Verdict: {guidance['verdict']}")
    st.write(guidance["reason"])
    st.write(f"Serving: {guidance['serving']}")
    st.write(f"Better swap: {guidance['better_swap']}")

    with st.expander("Rule breakdown"):
        if scoring["breakdown"]:
            st.table(scoring["breakdown"])
        else:
            st.write("No deterministic rules applied.")

    if product.get("barcode"):
        st.write("Save as:")
        cols = st.columns(3)
        for col, list_type in zip(cols, ["safe", "sometimes", "avoid"]):
            if col.button(list_type.title(), key=f"save_{barcode}_{list_type}"):
                db.save_food(
                    product["barcode"],
                    product.get("name") or product["barcode"],
                    guidance["adjusted_score"],
                    guidance["verdict"],
                    list_type,
                )
                st.success(f"Saved as {list_type}.")
    else:
        st.info("Save not available for label-scanned items in v1.")


def _saved_tab():
    foods = db.list_saved_foods()
    if not foods:
        st.info("No saved foods yet.")
        return
    for list_type in ["safe", "sometimes", "avoid"]:
        group = [food for food in foods if food["list_type"] == list_type]
        st.subheader(list_type.title())
        if not group:
            st.write("None")
            continue
        for food in group:
            cols = st.columns([4, 1])
            cols[0].write(f"{food['product_name']} — {food['score']}/10 — {food['verdict']}")
            if cols[1].button("Remove", key=f"remove_{food['barcode']}"):
                db.remove_saved_food(food["barcode"])
                _rerun()


def main():
    for key in ("NVIDIA_API_KEY", "SUPABASE_URL", "SUPABASE_ANON_KEY"):
        if not os.getenv(key):
            try:
                os.environ[key] = st.secrets[key]
            except (KeyError, FileNotFoundError):
                pass

    st.title("PCOS Food Scanner")
    profile = db.get_profile()
    if profile is None:
        st.info("Create your profile before scanning foods.")
        _profile_form()
        return

    scan_tab, saved_tab, profile_tab = st.tabs(["Scan", "Saved", "Profile"])
    with scan_tab:
        _scan_tab(profile)
    with saved_tab:
        _saved_tab()
    with profile_tab:
        _profile_form(profile)


if __name__ == "__main__":
    main()
