"""Regenerates the sample reference documents (TXT, DOCX, PDF) and sample_answers.json.

Run:  python data/samples/build_samples.py
(needs python-docx and reportlab, both in backend/requirements.txt)
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

EIFFEL = """The Eiffel Tower - Fact Sheet

The Eiffel Tower is a wrought-iron lattice tower on the Champ de Mars in Paris, France. It is named after the engineer Gustave Eiffel, whose company designed and built the tower.

Construction began in 1887 and was completed in 1889. The tower was built as the entrance arch to the 1889 World's Fair, which marked the centennial of the French Revolution.

The tower is 330 metres tall including its antennas. It was the tallest man-made structure in the world until the Chrysler Building in New York City was completed in 1930.

The tower has three levels for visitors. Tickets can be bought to ascend by stairs or by lift to the first and second levels.

The tower is repainted every seven years to protect it from rust. About 60 tonnes of paint are needed each time. Before the COVID-19 pandemic, the tower welcomed nearly seven million visitors each year.
"""

PHOTO_P1 = [
    "Photosynthesis: An Overview",
    "Photosynthesis is the process by which plants, algae and some bacteria convert light energy into chemical energy. "
    "In plants, photosynthesis takes place in the chloroplasts.",
    "Chloroplasts contain the green pigment chlorophyll, which absorbs mostly blue and red light and reflects green light. "
    "This is why leaves look green. The overall reaction uses carbon dioxide and water and produces glucose and oxygen.",
]
PHOTO_P2 = [
    "Photosynthesis has two stages. The light-dependent reactions occur in the thylakoid membranes and produce ATP and NADPH "
    "while releasing oxygen from water.",
    "The Calvin cycle, also called the light-independent reactions, takes place in the stroma and uses ATP and NADPH to build "
    "sugars from carbon dioxide.",
    "Plants take in carbon dioxide through small pores in their leaves called stomata. Photosynthesis does not occur in the "
    "mitochondria; mitochondria are the site of cellular respiration.",
]

SOLAR_P1 = [
    "Solar System Notes",
    "The Solar System formed about 4.6 billion years ago. It consists of the Sun and eight planets. Mercury is the closest "
    "planet to the Sun and the smallest planet.",
    "Venus is the hottest planet, with a surface temperature of about 465 degrees Celsius, because its thick carbon dioxide "
    "atmosphere traps heat.",
    "Earth is the third planet from the Sun and the only place in the universe known to support life. Mars has two small moons, "
    "Phobos and Deimos.",
]
SOLAR_P2 = [
    "Jupiter is the largest planet in the Solar System, and its mass is more than twice that of all the other planets combined.",
    "Saturn is famous for its extensive ring system, which is made mostly of ice particles. Uranus rotates on its side. "
    "Neptune is the farthest planet from the Sun.",
    "Light from the Sun takes about eight minutes and twenty seconds to reach Earth.",
]

ANSWERS = [
    {
        "id": "eiffel", "title": "Eiffel Tower (mixed answer)",
        "answer": "The Eiffel Tower was completed in 1889 and is located in Paris. It is 150 metres tall. The tower is repainted "
                  "every seven years. It was designed by the Italian sculptor Michelangelo. The tower's top-floor restaurant has "
                  "held three Michelin stars since 2015.",
        "expected": [
            {"text": "The Eiffel Tower was completed in 1889.", "label": "SUPPORTED"},
            {"text": "The Eiffel Tower is located in Paris.", "label": "SUPPORTED"},
            {"text": "The Eiffel Tower is 150 metres tall.", "label": "CONTRADICTED"},
            {"text": "The tower is repainted every seven years.", "label": "SUPPORTED"},
            {"text": "It was designed by the Italian sculptor Michelangelo.", "label": "CONTRADICTED"},
            {"text": "The tower's top-floor restaurant has held three Michelin stars since 2015.", "label": "INSUFFICIENT_EVIDENCE"},
        ],
    },
    {
        "id": "photosynthesis", "title": "Photosynthesis (mixed answer)",
        "answer": "Photosynthesis takes place in the chloroplasts. Chlorophyll reflects green light, which is why leaves look green. "
                  "Photosynthesis happens in the mitochondria. The process produces glucose and oxygen. Plants absorb carbon dioxide "
                  "through their stomata. Photosynthesis was first described by Aristotle.",
        "expected": [
            {"text": "Photosynthesis takes place in the chloroplasts.", "label": "SUPPORTED"},
            {"text": "Chlorophyll reflects green light, which is why leaves look green.", "label": "SUPPORTED"},
            {"text": "Photosynthesis happens in the mitochondria.", "label": "CONTRADICTED"},
            {"text": "The process produces glucose and oxygen.", "label": "SUPPORTED"},
            {"text": "Plants absorb carbon dioxide through their stomata.", "label": "SUPPORTED"},
            {"text": "Photosynthesis was first described by Aristotle.", "label": "INSUFFICIENT_EVIDENCE"},
        ],
    },
    {
        "id": "solar", "title": "Solar System (mixed answer)",
        "answer": "Jupiter is the largest planet in the Solar System. Venus is the hottest planet because of its thick atmosphere. "
                  "Mars has three moons. Mercury is the closest planet to the Sun and Neptune is the farthest. "
                  "Saturn has 146 confirmed moons.",
        "expected": [
            {"text": "Jupiter is the largest planet in the Solar System.", "label": "SUPPORTED"},
            {"text": "Venus is the hottest planet because of its thick atmosphere.", "label": "SUPPORTED"},
            {"text": "Mars has three moons.", "label": "CONTRADICTED"},
            {"text": "Mercury is the closest planet to the Sun.", "label": "SUPPORTED"},
            {"text": "Neptune is the farthest.", "label": "SUPPORTED"},
            {"text": "Saturn has 146 confirmed moons.", "label": "INSUFFICIENT_EVIDENCE"},
        ],
    },
]
NOTE = ("Expected labels are what a careful human reader would assign using the sample documents. "
        "The NLI model can disagree on individual claims; that is exactly why borderline cases are flagged for review.")


def build_docx(path: Path) -> None:
    import docx
    d = docx.Document()
    d.core_properties.title = "Photosynthesis: An Overview"
    d.core_properties.author = "TruthLens sample data"
    d.add_heading(PHOTO_P1[0], level=1)
    for t in PHOTO_P1[1:]:
        d.add_paragraph(t)
    d.add_page_break()
    for t in PHOTO_P2:
        d.add_paragraph(t)
    d.save(path)


def build_pdf(path: Path) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
    ss = getSampleStyleSheet()
    story = [Paragraph(SOLAR_P1[0], ss["Title"])]
    for t in SOLAR_P1[1:]:
        story += [Paragraph(t, ss["BodyText"]), Spacer(1, 8)]
    story.append(PageBreak())
    for t in SOLAR_P2:
        story += [Paragraph(t, ss["BodyText"]), Spacer(1, 8)]
    SimpleDocTemplate(str(path), pagesize=A4, title="Solar System Notes", author="TruthLens sample data").build(story)


if __name__ == "__main__":
    (HERE / "eiffel_tower_factsheet.txt").write_text(EIFFEL, encoding="utf-8")
    build_docx(HERE / "photosynthesis_overview.docx")
    build_pdf(HERE / "solar_system_notes.pdf")
    (HERE / "sample_answers.json").write_text(json.dumps({"note": NOTE, "answers": ANSWERS}, indent=2), encoding="utf-8")
    print("Sample files written to", HERE)
