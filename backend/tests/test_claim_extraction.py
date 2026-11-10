from app.services.claim_extraction import claims_from_user, extract_claims
from app.services.text_utils import split_sentences


def texts(answer, **kw):
    return [c.text for c in extract_claims(answer, **kw)]


def test_sentence_splitter_handles_abbreviations_and_decimals():
    s = split_sentences("Dr. J. K. Smith paid $3.5 million. The U.S. economy grew. It is e.g. fine.")
    assert len(s) == 3 and s[0].startswith("Dr. J. K. Smith")


def test_one_claim_per_sentence_with_ids_and_context():
    cl = extract_claims("Paris is the capital of France. Berlin is the capital of Germany.")
    assert [c.id for c in cl] == ["C1", "C2"]
    assert cl[1].sentence == "Berlin is the capital of Germany."
    assert cl[0].sentence_id == 1 and cl[1].sentence_id == 2


def test_compound_predicate_is_split_with_shared_subject():
    t = texts("The Eiffel Tower was completed in 1889 and is located in Paris.")
    assert t == ["The Eiffel Tower was completed in 1889.", "The Eiffel Tower is located in Paris."]


def test_independent_clauses_and_semicolons_split():
    assert len(texts("Mercury is the closest planet to the Sun and Neptune is the farthest planet.")) == 2
    assert len(texts("Jupiter is a gas giant; Mars is a rocky planet.")) == 2


def test_noun_coordination_not_split():
    t = texts("France, Germany and Italy are members of the European Union.")
    assert len(t) == 1


def test_split_can_be_disabled():
    assert len(texts("The tower was built in 1889 and is in Paris.", split_compound=False)) == 1


def test_questions_chitchat_and_short_text_are_skipped():
    a = "Sure! Here is the answer. What is the capital? Hi. The Nile is the longest river in Africa."
    assert texts(a) == ["The Nile is the longest river in Africa."]


def test_discourse_markers_and_citations_stripped():
    assert texts("However, water boils at 100 degrees Celsius [1].") == ["Water boils at 100 degrees Celsius."]


def test_pronoun_resolution_uses_previous_subject():
    cl = extract_claims("The Eiffel Tower is in Paris. It is 330 metres tall.")
    assert cl[1].text == "The Eiffel Tower is 330 metres tall." and cl[1].resolved_pronoun
    cl2 = extract_claims("The Eiffel Tower is in Paris. It is 330 metres tall.", resolve_pronouns=False)
    assert cl2[1].text.startswith("It is")


def test_max_claims_and_empty_input():
    ans = " ".join(f"Item {i} is located in city {i}." for i in range(20))
    assert len(extract_claims(ans, max_claims=5)) == 5
    assert extract_claims("") == [] and extract_claims("   ") == []


def test_user_claims_get_unique_ids_and_skip_blank():
    cl = claims_from_user([{"id": "C1", "text": "A is B."}, {"id": "C1", "text": "C is D."}, {"text": "  "}])
    assert len(cl) == 2 and cl[0].id != cl[1].id and all(c.source == "user" for c in cl)
