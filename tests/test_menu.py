from wareon import keyboards


def _datas(markup):
    return [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data]


def test_main_menu_has_core_buttons():
    datas = _datas(keyboards.main_menu())
    for expected in ("menu:agent", "menu:pulse", "menu:sale", "menu:report", "menu:settings"):
        assert expected in datas


def test_panel_period_buttons():
    datas = _datas(keyboards.panel_period_kb())
    assert "pulse:7" in datas and "pulse:30" in datas
    assert "menu:main" in datas


def test_report_period_buttons():
    datas = _datas(keyboards.report_kb())
    assert "report:7" in datas and "report:30" in datas


def test_settings_marks_current_level():
    kb = keyboards.settings_kb("autopilot")
    texts = [b.text for row in kb.inline_keyboard for b in row]
    autopilot = next(t for t in texts if "Автопилот" in t)
    semi = next(t for t in texts if "Полу-автоном" in t)
    assert autopilot.startswith("✅")
    assert not semi.startswith("✅")
    assert "auto:autopilot" in _datas(kb)


def test_back_menu():
    assert "menu:main" in _datas(keyboards.back_menu())


def test_onboarding_keyboards():
    assert "onb:features" in _datas(keyboards.onboarding_kb())
    assert "menu:main" in _datas(keyboards.onboarding_kb())
    assert "menu:main" in _datas(keyboards.features_kb())
