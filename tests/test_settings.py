from taxi import settings


def test_list_setting_single_value():
    l = settings.ListSetting()
    assert l.to_python('foo') == ['foo']


def test_list_setting_multiple_values():
    l = settings.ListSetting()
    assert l.to_python('foo, bar') == ['foo', 'bar']


def test_list_setting_removes_empty_elements():
    l = settings.ListSetting()
    assert l.to_python('foo, ,bar,,') == ['foo', 'bar']


def test_int_setting_casts_to_int():
    l = settings.IntegerSetting()
    assert l.to_python('42') == 42


def test_integer_list_setting_casts_to_int():
    l = settings.IntegerListSetting()
    assert l.to_python('42, 12') == [42, 12]
