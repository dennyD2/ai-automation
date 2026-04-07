def validate_result(description, expectation, text):
    prompt = f"""
You are a QA tester.

Test case:
{description}

Expected result:
{expectation}

Actual UI text:
{text}

Instructions:

1. Use the description to understand what action likely happened.
   (Example: login → implies user clicked login button)

2. ONLY validate based on the expected result.

3. Do NOT evaluate UX improvements or additional issues.

4. Do NOT overthink beyond expectation.

Rules:
- If expected message is present → PASS
- If not present → FAIL
- Ignore other possible improvements or issues

Return:

Result: PASS or FAIL
Reason: Short explanation strictly based on expectation
"""
    response = llm.invoke(prompt)
    return response.content
