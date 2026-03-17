from pathlib import Path
import argparse
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = PROJECT_ROOT / ".browser" / "antxiaoer"


def build_driver(headless: bool) -> webdriver.Chrome:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument(f"--user-data-dir={PROFILE_DIR}")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1440,1200")

    return webdriver.Chrome(options=options)


def wait_click(wait: WebDriverWait, xpath: str) -> None:
    element = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
    element.click()


def open_login(driver: webdriver.Chrome) -> None:
    driver.get("https://www.yxiaoer.cn/")
    wait = WebDriverWait(driver, 20)
    wait_click(wait, "//button[contains(., '登录/注册')]")


def select_sms_login(driver: webdriver.Chrome) -> None:
    wait = WebDriverWait(driver, 20)
    wait_click(wait, "//*[contains(text(),'验证码登录')]")


def fill_phone(driver: webdriver.Chrome, phone: str) -> None:
    wait = WebDriverWait(driver, 20)
    phone_input = wait.until(
        EC.presence_of_element_located((By.XPATH, "//input[@type='tel']"))
    )
    phone_input.clear()
    phone_input.send_keys(phone)


def click_send_code(driver: webdriver.Chrome) -> None:
    wait = WebDriverWait(driver, 20)
    wait_click(wait, "//*[contains(text(),'获取验证码') or contains(text(),'发送验证码')]")


def fill_code(driver: webdriver.Chrome, code: str) -> None:
    wait = WebDriverWait(driver, 20)
    code_input = wait.until(
        EC.presence_of_element_located(
            (
                By.XPATH,
                "//input[contains(@placeholder,'验证码') or @maxlength='6']",
            )
        )
    )
    code_input.clear()
    code_input.send_keys(code)


def submit_login(driver: webdriver.Chrome) -> None:
    wait = WebDriverWait(driver, 20)
    submit = wait.until(
        EC.element_to_be_clickable(
            (
                By.XPATH,
                "//*[@role='dialog']//button[@type='submit' and contains(.,'登 录')]",
            )
        )
    )
    driver.execute_script("arguments[0].click();", submit)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phone", help="Phone number for SMS login")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--send-code", action="store_true")
    parser.add_argument("--auto-submit", action="store_true")
    args = parser.parse_args()

    driver = build_driver(args.headless)
    try:
        open_login(driver)
        select_sms_login(driver)
        if args.phone:
            fill_phone(driver, args.phone)
            print("Phone number filled.")
            if args.send_code:
                click_send_code(driver)
                print("SMS code requested.")

        if args.auto_submit:
            code = input("Enter SMS code: ").strip()
            fill_code(driver, code)
            submit_login(driver)
            print("Login submitted.")

        print("Browser is ready for SMS login.")
        print("Complete the verification flow, then press Enter here to keep the session open for 30 seconds.")
        input()
        time.sleep(30)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
