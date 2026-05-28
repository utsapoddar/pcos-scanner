"""Streamlit entry for the PCOS Food Scanner prototype."""

from dotenv import load_dotenv
import os
import streamlit as st

from core import db
from core.migrations import run_pending_migrations
from core.openfoodfacts import fetch_product
from core.vision import extract_product_from_label
from core.food_photo import aggregate_meal, estimate_meal_from_photo
from core.personalize import personalize
from core.profile import PCOS_TYPES, SYMPTOM_FIELDS, Profile
from core.scoring import score_food

try:
    from core.barcode import decode_barcode
except ImportError:
    decode_barcode = None

load_dotenv()


def _bridge_streamlit_secrets():
    for key in (
        "NVIDIA_API_KEY",
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_DB_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
    ):
        if not os.getenv(key):
            try:
                os.environ[key] = st.secrets[key]
            except (KeyError, FileNotFoundError):
                pass


_bridge_streamlit_secrets()
_MIGRATION_ERROR = None
try:
    run_pending_migrations()
except Exception as exc:
    _MIGRATION_ERROR = str(exc)


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


def _meal_tab(profile):
    camera_image = st.camera_input("Meal photo", key="meal_camera_photo")
    upload_image = st.file_uploader("Or upload a meal photo", type=["jpg", "jpeg", "png"], key="meal_upload_photo")
    image = camera_image or upload_image
    if image is None and "meal_items" not in st.session_state:
        return

    if image is not None:
        image_bytes = image.getvalue()
        if st.session_state.get("meal_photo_bytes") != image_bytes:
            with st.spinner("Estimating meal..."):
                items = estimate_meal_from_photo(image_bytes)
            if items is None:
                st.error("Could not read the meal photo.")
                return
            st.session_state["meal_photo_bytes"] = image_bytes
            st.session_state["meal_items"] = items
            st.session_state["meal_photo_version"] = st.session_state.get("meal_photo_version", 0) + 1

    items = st.session_state.get("meal_items") or []
    if not items:
        st.warning("No food items found in the photo.")
        return

    mode = st.radio("Meal weights", ["Estimate from photo", "I weighed it"], horizontal=True)
    grams_by_index = None
    if mode == "I weighed it":
        grams_by_index = {}
        version = st.session_state.get("meal_photo_version", 0)
        for index, item in enumerate(items):
            grams_by_index[index] = st.number_input(
                item.get("name") or f"Item {index + 1}",
                min_value=0.0,
                value=float(item.get("est_grams") or 0),
                step=1.0,
                key=f"meal_grams_{version}_{index}",
            )
    else:
        st.info("AI photo estimates can be wrong. Use weighed mode when you need more accurate calories/macros.")

    meal = aggregate_meal(items, grams_by_index)
    names = ", ".join(row["name"] for row in meal["items"])
    product = {
        "name": f"Meal: {names}",
        "nutriments_100g": meal["nutriments_100g"],
        "nova_group": meal["nova_group"],
    }
    scoring = score_food(product["nutriments_100g"], product["nova_group"])
    guidance = personalize(scoring["score"], scoring["breakdown"], product, profile)

    st.subheader(product["name"])
    st.table([{"name": row["name"], "grams": row["grams"], "kcal": row["kcal"]} for row in meal["items"]])
    st.write(f"Total kcal: {meal['totals']['kcal']}")
    st.write(f"Protein: {meal['totals']['proteins_g']}g")
    st.write(f"Fibre: {meal['totals']['fiber_g']}g")
    st.write(f"Sugars: {meal['totals']['sugars_g']}g")
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
    _bridge_streamlit_secrets()

    st.title("PCOS Food Scanner")
    if _MIGRATION_ERROR:
        st.warning(f"Supabase migrations failed: {_MIGRATION_ERROR}")
    profile = db.get_profile()
    if profile is None:
        st.info("Create your profile before scanning foods.")
        _profile_form()
        return

    scan_tab, meal_tab, saved_tab, profile_tab = st.tabs(["Scan", "Meal", "Saved", "Profile"])
    with scan_tab:
        _scan_tab(profile)
    with meal_tab:
        _meal_tab(profile)
    with saved_tab:
        _saved_tab()
    with profile_tab:
        _profile_form(profile)


if __name__ == "__main__":
    main()
