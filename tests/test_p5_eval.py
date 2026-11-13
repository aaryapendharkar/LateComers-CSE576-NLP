import json

from src.common import io
from src.common.edits import apply_edit
from src.common.tables import doc_to_text
from src.defenses.img_text_check import evaluate


def _page(pid, doc_id, variant, iv, tv):
    return {"page_id": pid, "doc_id": doc_id, "variant": variant, "image_version": iv, "text_version": tv,
            "pdf_path": f"{pid}.pdf", "image_path": f"{pid}.png", "text_path": f"{pid}.txt"}


def test_evaluate_oracle(cfg, tmp_path):
    docs = io.load_docs(cfg)
    atk = io.load_attacks(cfg)["G2_text_only_table_q0001"]
    manifests, parsed = tmp_path / "manifests", tmp_path / "parsed" / "docling"
    manifests.mkdir()
    parsed.mkdir(parents=True)
    recs = []
    for doc_id, d in docs.items():
        pid = f"{doc_id}__clean"
        recs.append(_page(pid, doc_id, "clean", "clean", "clean"))
        (parsed / f"{pid}.txt").write_text(doc_to_text(d.to_dict()))
    doc = docs["finqa_ACME_2019_p12"].to_dict()
    recs.append(_page(atk.poison_page_id, doc["doc_id"], atk.attack_id, "clean", "poison"))
    (parsed / f"{atk.poison_page_id}.txt").write_text(doc_to_text(apply_edit(doc, atk.edit)))
    (manifests / "pages_test.jsonl").write_text("\n".join(json.dumps(r) for r in recs))

    run_cfg = {**cfg, "paths": {**cfg["paths"], "manifests_dir": str(manifests),
                                "parsed_dir": str(tmp_path / "parsed")},
               "img_text_check": {"text_source": "docling", "cache_dir": str(tmp_path / "cache")}}
    rows = {r["kind"]: r for r in evaluate(run_cfg, n_clean=10, oracle=True, out_dir=str(tmp_path / "out"))}

    assert rows["clean_table"]["rate"] == 0.0 and rows["clean_table"]["n"] == 3
    assert rows["clean_chart"]["rate"] == 0.0
    assert rows["text_only_table"]["rate"] == 1.0 and rows["text_only_table"]["errors"] == 0
    assert (tmp_path / "out" / "checker_table_oracle.md").exists()
    assert not (tmp_path / "cache").exists()
    again = {r["kind"]: r for r in evaluate(run_cfg, n_clean=10, oracle=True, out_dir=str(tmp_path / "out"))}
    assert again["text_only_table"]["n"] == 1
