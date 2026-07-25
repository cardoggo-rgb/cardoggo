Traceback (most recent call last):
  File "/home/runner/work/cardoggo/cardoggo/agent.py", line 277, in generate_article
[2026-07-25 10:05:39] Selected topic: Classic Muscle Cars That Are Still Affordable  (category: Classic Cars)
[2026-07-25 10:05:39] Generating article with Claude...
    article = json.loads(raw, strict=False)
              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/json/__init__.py", line 359, in loads
    return cls(**kw).decode(s)
           ^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/json/decoder.py", line 338, in decode
    obj, end = self.raw_decode(s, idx=_w(s, 0).end())
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.12.13/x64/lib/python3.12/json/decoder.py", line 356, in raw_decode
    raise JSONDecodeError("Expecting value", s, err.value) from None
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/home/runner/work/cardoggo/cardoggo/agent.py", line 405, in <module>
    main()
  File "/home/runner/work/cardoggo/cardoggo/agent.py", line 371, in main
    article = generate_article(topic)
              ^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/runner/work/cardoggo/cardoggo/agent.py", line 279, in generate_article
    raise RuntimeError(f"Could not parse article JSON from model output: {e}\n---\n{raw[:2000]}")
RuntimeError: Could not parse article JSON from model output: Expecting value: line 1 column 1 (char 0)
---
Now I have enough grounded data to write the article.
Now I have plenty of grounded material to write a solid, well-cited article.
Now I have plenty of solid, grounded data. Let me write the article.
Now I have plenty of solid, well-sourced material. Time to write the final article.
Now I have comprehensive, well-sourced data. Let me compose the final article.

{
"title": "Muscle Car Dreams on a Budget: Classic American Muscle You Can Still Afford in 2026",
"meta_description": "From the Nova SS to the Pontiac GTO, here are real classic muscle cars you can still buy today without needing a lottery win.",
"content_html": "<p>Watch enough classic car auctions and you'd think every muscle car worth owning costs more than a house down payment. It's true that some legends have gone stratospheric — but plenty of genuinely fun, V8-powered classics are still sitting well within reach of everyday budgets. You just have to know where to look, and be willing to skip the most famous nameplates in favor of their less-hyped siblings.</p>

<h2>Why Some Muscle Cars Are Cheap and Others Aren't</h2>
<p>Before diving into specific cars, it helps to understand what actually drives classic muscle car pricing. A few basic rules apply across the board:</p>
<ul>
<li><strong>Production numbers matter.</strong> <span>
Cars produced in large volumes naturally cost less today, and when thousands of examples still exist, scarcity doesn't inflate prices.
</span></li>
<li><strong>Engine choice makes a huge difference.</strong> 
Base engines matter — inline-six and small-block V8 cars cost far less than big-block, performance-trim versions.
</li>
<li><strong>Brand popularity inflates prices.</strong> 
Everyone chases Mustangs and Camaros, while fewer buyers chase AMC, Mercury, or Buick muscle cars — which is exactly why they're cheaper.
</li>
</ul>

<h2>Classic Muscle Cars Still Within Reach</h2>

<h3>Chevrolet Nova SS</h3>
<p>The Nova often lives in the shadow of its bigger sibling, the Chevelle, 
Error: Process completed with exit code 1.
