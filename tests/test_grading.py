from app import grading


def test_default_scale_is_zero_to_five_levels() -> None:
    scale = grading.normalize(None)
    assert scale == {"max": 5, "labels": grading.DEFAULT_LABELS}
    assert grading.levels(scale) == [0, 1, 2, 3, 4, 5]
    assert grading.label(scale, 5) == "Perfect"
    assert grading.label(scale, 0) == "False or absent"


def test_default_scale_is_copied_not_shared() -> None:
    """Callers must not be able to mutate the module default through a normalized scale."""
    scale = grading.normalize(None)
    scale["labels"][5] = "Broken"
    assert grading.normalize(None)["labels"][5] == "Perfect"


def test_normalize_cleans_labels_and_bounds() -> None:
    scale = grading.normalize(
        {"max": 10, "labels": {"3": "Bad", "11": "Nope", "x": "Nope", "7": ""}}
    )
    assert scale == {"max": 10, "labels": {3: "Bad"}}


def test_normalize_falls_back_on_bad_max() -> None:
    assert grading.normalize({"max": 0})["max"] == 5
    assert grading.normalize({"max": "ten"})["max"] == 5
    assert grading.normalize({"max": True})["max"] == 5


def test_scheduler_rating_maps_onto_one_to_four() -> None:
    scale = {"max": 4, "labels": {}}
    assert [grading.scheduler_rating(scale, level) for level in range(5)] == [1, 2, 3, 3, 4]
    five = {"max": 5, "labels": {}}
    assert [grading.scheduler_rating(five, level) for level in range(6)] == [1, 2, 2, 3, 3, 4]
    ten = {"max": 10, "labels": {}}
    assert grading.scheduler_rating(ten, 0) == 1
    assert grading.scheduler_rating(ten, 10) == 4
    assert grading.scheduler_rating(ten, 99) == 4
    assert grading.scheduler_rating(ten, -3) == 1


def test_label_lookup() -> None:
    scale = {"max": 10, "labels": {3: "Bad"}}
    assert grading.label(scale, 3) == "Bad"
    assert grading.label(scale, 4) == ""
