# ShopFloor Copilot — FDE Decision Rationale

My answers to Section G of the assignment, and the reason for the learning-loop setting that Section E asks for. Every choice, with the options I looked at and the test results, is in [DECISION_LOG.md](DECISION_LOG.md).

## 1. Vector RAG vs. a long-context read

I chose vector RAG because a plant's SOPs keep growing and changing, and every answer on a shop floor must say which rule it came from. So I cut each SOP into its numbered sections, find the few that match, and let the model answer only from those. I also measured the cost: the top 3 sections need 495 tokens, while my whole five-document set needs 2,954, which is six times more. For a 20-page set that becomes about 16,000 tokens, over 30 times more work for every question. If the SOP set were fixed at 20 pages, I would not use retrieval at all: I would give the model the whole set once, reuse that, and never miss a rule. That matters, because in my test the first search result was the wrong section in 4 of 21 questions.

## 2. Agent loop vs. a fixed pipeline, and what I would not make agentic

Workers ask in many different ways: sometimes with a photo, sometimes without, sometimes about the part, sometimes about who to call. One fixed path cannot fit all of that, so the model picks the next tool, and my code writes down each step and its reason as it happens. The one part I do not leave to the model is the accept, rework or scrap decision. The model only reads the limits from the SOP; normal code compares the measurement with them. I learned this from testing: when I let the model do everything in one go, two models got only 6 and 9 of 19 cases right, and one wrong comparison means a bad part is shipped.

## 3. Classical CV, a pretrained model, or both

I used classical OpenCV only. The code finds the part, measures it, and looks for a line: a straight thin line is a scratch, and a wandering one is a crack. I chose this because the brief wants to see the technique, and because rules give me a measurement in millimetres and a reason I can show in the record. A ready-made model knows everyday objects, not scratches, and training was not allowed. I must be honest about the result: 100 out of 100 is on images I generated myself, so it does not prove the rules work on real parts. I would train a custom model when real photos show the rules failing under different lighting, and I have a few hundred labelled photos per defect type.

## 4. The first cost lever when scaling from one plant to ten

I would use caching first, and a specific kind: saving the limits the model reads from each SOP section. When a worker sends a photo, the model's only job is to copy the limits from the SOP, and it gives the same output every time for the same section. If I save that output, most photo checks need no model call at all, and the quality does not change. When a section is revised, I throw away its saved limits. I would not start with the other levers: the small model got only 15 of 19 right, the models from Ollama are already quantized, batching makes a worker wait, and a fine-tuned model needs real data that a pilot does not have.

## 5. A shop-floor governance risk this design does not yet address

A part ID that is read wrongly can still look correct, and then a defect is recorded against the wrong work order. In my harder image test, 3 of 100 IDs were read with one wrong digit, for example `WO-38522` when the part said `WO-38322`, and the system accepted them because the format was right. On a shop floor this is serious: the wrong work order is held or scrapped, and the real bad part moves on with a clean record. My audit record would even store the wrong ID faithfully, so the mistake would look verified. In a real project I would add a check digit to the ID, check with the work-order system that the order is open at that station, and ask the operator to confirm the ID before any hold or scrap.

## Action axis for the learning loop (Section E)

I chose the RAG top-K as the setting to learn, with 1, 3 or 5 passages, and not the OCR engine. Top-K changes every answer, even for a question without a photo, and it changes the thing the worker gives a thumbs up or down for. It also has a real trade-off: in my test the right section was found 17 of 21 times with 1 passage and 21 of 21 with 5, but more passages take longer to read. When I replayed real answers, the system learned different values for different defects: for scratches it moved from 1 passage to 3, and for size problems from 3 to 1. My laptop is slow, so I divided the measured seconds by 20 for this replay, and the README shows the result both ways.
