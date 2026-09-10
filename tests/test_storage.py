import sqlite3

import pytest

from data.storage import InvalidJobData, JobStorage


def test_job_persistence_preserves_each_explicit_source(storage, job_data):
    for source in ("WTTJ", "Greenhouse", "Lever"):
        record = {**job_data, "url": f"{job_data['url']}-{source}", "source": source}
        assert storage.save_one(record) is True

    saved = {job["source"] for job in storage.all(order_by="title ASC")}
    assert saved == {"WTTJ", "Greenhouse", "Lever"}
    assert storage.count() == 3
    assert storage.is_saved(job_data["url"] + "-WTTJ")
    assert storage.saved_urls() == {
        f"{job_data['url']}-{source}"
        for source in ("WTTJ", "Greenhouse", "Lever")
    }


@pytest.mark.parametrize(
    "missing_or_invalid",
    [
        {},
        {"source": ""},
        {"source": "Unknown"},
        {"source": None},
    ],
)
def test_job_persistence_rejects_missing_or_invalid_source(
    storage,
    job_data,
    missing_or_invalid,
):
    record = dict(job_data)
    record.update(missing_or_invalid)
    if not missing_or_invalid:
        record.pop("source")

    with pytest.raises(InvalidJobData):
        storage.save_one(record)

    assert storage.count() == 0


def test_job_persistence_rejects_invalid_shapes(storage, job_data):
    with pytest.raises(InvalidJobData, match="JSON object"):
        storage.save_one(None)

    with pytest.raises(InvalidJobData, match="URL cannot be empty"):
        storage.save_one({**job_data, "url": " "})

    with pytest.raises(InvalidJobData, match="salary must be a string"):
        storage.save_one({**job_data, "salary": 100})


def test_job_persistence_preserves_nullable_values_and_unicode(storage, job_data):
    record = {
        **job_data,
        "title": "Ingénieur logiciel",
        "location": "Île-de-France",
        "salary": None,
    }
    assert storage.save_one(record) is True

    stored = storage.all()[0]
    assert stored["title"] == "Ingénieur logiciel"
    assert stored["location"] == "Île-de-France"
    assert stored["salary"] is None


def test_duplicate_url_is_idempotent(storage, job_data):
    assert storage.save_one(job_data) is True
    assert storage.save_one(job_data) is False
    assert storage.count() == 1


def test_labels_are_trimmed_sorted_and_deduplicated(storage, job_data):
    storage.save_one(job_data)
    storage.add_label(job_data["url"], "  Favorite ")
    storage.add_label(job_data["url"], "Favorite")
    storage.add_label(job_data["url"], "à postuler")
    storage.add_label(job_data["url"], "")

    assert storage.labels_for_job(job_data["url"]) == ["Favorite", "à postuler"]
    assert storage.all_labels() == ["Favorite", "à postuler"]


def test_labels_require_a_saved_job_and_string_value(storage, job_data):
    with pytest.raises(InvalidJobData, match="label must be a string"):
        storage.add_label(job_data["url"], None)

    with pytest.raises(InvalidJobData, match="not saved"):
        storage.add_label(job_data["url"], "Favorite")


def test_delete_cascades_associations_but_retains_label_vocabulary(storage, job_data):
    storage.save_one(job_data)
    storage.add_label(job_data["url"], "Favorite")

    assert storage.delete_one(job_data["url"]) is True
    assert storage.delete_one(job_data["url"]) is False
    assert storage.labels_for_job(job_data["url"]) == []
    assert storage.all_labels() == ["Favorite"]


def test_clear_removes_jobs_and_associations_but_retains_labels(storage, job_data):
    storage.save_one(job_data)
    storage.add_label(job_data["url"], "Favorite")

    storage.clear()

    assert storage.count() == 0
    assert storage.saved_urls() == set()
    assert storage.all_labels() == ["Favorite"]


def test_order_by_is_whitelisted(storage, job_data):
    storage.save_one(job_data)

    with pytest.raises(ValueError):
        storage.all("published_at DESC; DROP TABLE jobs")

    assert storage.count() == 1


def test_database_is_created_with_parent_directory(tmp_path, job_data):
    db_path = tmp_path / "nested" / "jobs.db"
    with JobStorage(db_path) as instance:
        instance.save_one(job_data)
        assert instance.count() == 1


def test_legacy_database_gets_wttj_source_and_foreign_keys(tmp_path):
    db_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE jobs (
            url TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            location TEXT,
            published_at TEXT,
            contract_type TEXT,
            remote TEXT,
            salary TEXT
        );
        CREATE TABLE labels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL UNIQUE
        );
        CREATE TABLE job_label (
            job_url TEXT NOT NULL,
            label_id INTEGER NOT NULL,
            PRIMARY KEY (job_url, label_id)
        );
        INSERT INTO jobs VALUES (
            'https://jobs.example.test/legacy',
            'Legacy job',
            'Example',
            'Paris',
            '',
            '',
            '',
            NULL
        );
        """
    )
    connection.commit()
    connection.close()

    with JobStorage(db_path) as storage:
        stored = storage.all()
        assert stored[0]["source"] == "WTTJ"
        foreign_keys = storage._conn.execute(
            "PRAGMA foreign_key_list(job_label)"
        ).fetchall()
        assert len(foreign_keys) == 2


def test_invalid_job_data_does_not_leave_a_partial_transaction(storage, job_data):
    invalid = {**job_data, "title": 42}
    with pytest.raises(InvalidJobData):
        storage.save_one(invalid)

    assert storage.count() == 0
