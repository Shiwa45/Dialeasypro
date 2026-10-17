"""
The Gemini model the AI call summary uses.

Google stopped serving the 2.5 models to projects that had not used them, so
summaries failed with "model is deprecated". The default is now a current
model, and GEMINI_MODEL still overrides it.
"""
from django.conf import settings
from django.test import override_settings

from apps.ai.services.gemini import DEFAULT_MODEL, model_name, transcribe_model_name


def test_the_default_is_not_a_retired_2_5_model():
    assert "2.5" not in DEFAULT_MODEL
    assert "2.5" not in settings.GEMINI_MODEL


def test_settings_and_service_agree_on_the_default():
    assert settings.GEMINI_MODEL == DEFAULT_MODEL


@override_settings(GEMINI_MODEL="gemini-x-flash", GEMINI_TRANSCRIBE_MODEL="")
def test_gemini_model_overrides_both_halves():
    assert model_name() == "gemini-x-flash"
    assert transcribe_model_name() == "gemini-x-flash"


@override_settings(GEMINI_MODEL="gemini-x-flash", GEMINI_TRANSCRIBE_MODEL="gemini-y")
def test_transcription_can_use_its_own_model():
    assert transcribe_model_name() == "gemini-y"
