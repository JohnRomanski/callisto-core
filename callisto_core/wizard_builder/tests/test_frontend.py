from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait

from callisto_core.wizard_builder import view_helpers


class NavigatingElement:
    """A button that loads a new page; click() waits for that page"""

    def __init__(self, browser, element):
        self.browser = browser
        self.element = element

    def click(self):
        # mark the current page; a newly loaded page won't have the mark.
        # (waiting for a stale element is flaky: chrome sometimes reports a
        # replaced node with a generic error instead of a stale reference)
        self.browser.execute_script("window._callistoOldPage = true;")
        self.element.click()
        WebDriverWait(self.browser, 10).until(
            lambda driver: driver.execute_script(
                "return document.readyState === 'complete'"
                " && window._callistoOldPage === undefined;"
            )
        )

    def __getattr__(self, name):
        return getattr(self.element, name)


class ElementHelper:
    def __init__(self, browser):
        self.browser = browser

    @property
    def done(self):
        return NavigatingElement(
            self.browser,
            self.browser.find_element(
                By.CSS_SELECTOR, f'[value="{view_helpers.StepsHelper.review_name}"]'
            ),
        )

    @property
    def next(self):
        return NavigatingElement(
            self.browser,
            self.browser.find_element(
                By.CSS_SELECTOR, f'[value="{view_helpers.StepsHelper.next_name}"]'
            ),
        )

    @property
    def back(self):
        return NavigatingElement(
            self.browser,
            self.browser.find_element(
                By.CSS_SELECTOR, f'[value="{view_helpers.StepsHelper.back_name}"]'
            ),
        )

    @property
    def extra_input(self):
        return self.browser.find_element(By.CSS_SELECTOR, "#id_question_1_0")

    @property
    def extra_dropdown(self):
        return self.browser.find_element(By.CSS_SELECTOR, "#id_question_1_1")

    @property
    def dropdown_select(self):
        return self.browser.find_element(
            By.CSS_SELECTOR, "select.extra-widget-dropdown"
        )

    @property
    def choice_1(self):
        return self.choice_number(0)

    @property
    def choice_3(self):
        return self.choice_number(2)

    @property
    def text_input(self):
        return self.browser.find_element(By.CSS_SELECTOR, '[type="text"]')

    def wait_for_display(self):
        # / really unreliable way to wait for the element to be displayed
        self.next.click()
        self.back.click()

    def choice_number(self, number):
        return self.browser.find_elements(By.CSS_SELECTOR, '[type="checkbox"]')[number]
