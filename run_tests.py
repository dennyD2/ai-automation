async def smart_find_and_act(page, action, target, value=""):
    target = target.lower()

    try:
        if action == "fill":
            # try multiple strategies
            locator = (
                page.get_by_placeholder(target)
                or page.get_by_label(target)
                or page.locator(f'input[name*="{target}"]')
                or page.locator(f'input[id*="{target}"]')
            )
            await locator.first.fill(value)
            await locator.first.press("Tab")

        elif action == "click":
            locator = (
                page.get_by_role("button", name=target)
                or page.get_by_text(target)
                or page.locator(f'button[id*="{target}"]')
                or page.locator(f'button')
            )
            await locator.first.click()

    except Exception as e:
        print(f"⚠️ Smart action failed: {action} {target} → {e}")
