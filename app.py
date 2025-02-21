import streamlit as st
import pandas as pd
import re
import csv
import time
from datetime import datetime
from playwright.sync_api import Playwright, sync_playwright, expect

def extract_course_dates(page) -> list:
    dates = []
    try:
        # Wait for table to be visible after partner selection
        page.wait_for_selector("table", timeout=5000)
        # Look for date elements in the table
        rows = page.locator("table tr").all()
        for row in rows[1:]:  # Skip header row
            cells = row.locator("td").all()
            if len(cells) >= 3:  # Ensure we have enough cells
                try:
                    date = cells[0].inner_text()
                    location = cells[1].inner_text()
                    language = cells[2].inner_text()
                    if date and date.strip():  # Only add if date is not empty
                        dates.append([date.strip(), location.strip(), language.strip()])
                except Exception as e:
                    st.error(f"Error extracting row data: {e}")
                    continue
    except Exception as e:
        st.error(f"Error extracting dates: {e}")
    return dates

def process_courses(email: str, password: str) -> pd.DataFrame:
    results = []
    
    # Create status containers
    status = st.empty()
    progress = st.progress(0)
    course_status = st.empty()
    
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)  # Run headless for Streamlit
        context = browser.new_context()
        page = context.new_page()
        
        try:
            # Login phase - 10%
            status.write("Phase 1/4: Logging in...")
            progress.progress(0.05)
            page.goto("https://www.epiclearningnetwork.com/")
            page.get_by_role("textbox", name="Email").fill(email)
            page.get_by_role("textbox", name="Password").fill(password)
            page.get_by_role("button", name="Login").click()
            progress.progress(0.1)
            
            # Navigate to courses - 20%
            status.write("Phase 2/4: Getting course list...")
            page.get_by_role("link", name="Courses").click()
            page.wait_for_load_state("networkidle")
            progress.progress(0.2)
            
            # Get all courses and their view links
            courses = []
            view_dates_links = page.get_by_role("link", name=re.compile("View", re.IGNORECASE)).all()
            
            for link in view_dates_links:
                try:
                    course_row = link.locator("xpath=../..") # Go up to the row
                    course_name = course_row.locator("td").first.inner_text().strip()
                    view_url = link.get_attribute('href')
                    if view_url:
                        if not view_url.startswith('https://'):
                            view_url = f"https://www.epiclearningnetwork.com{view_url}"
                        courses.append((course_name, view_url))
                except Exception as e:
                    st.error(f"Error getting course info: {e}")
                    continue
            
            total_courses = len(courses)
            status.write(f"Phase 3/4: Processing {total_courses} courses...")
            
            # Process each course sequentially - 20% to 90%
            course_progress_range = 0.7  # 70% of total progress
            for i, (course_name, view_url) in enumerate(courses, 1):
                try:
                    # Calculate overall progress (20% base + proportional progress through courses)
                    current_progress = 0.2 + (course_progress_range * (i / total_courses))
                    progress.progress(current_progress)
                    course_status.write(f"Course {i}/{total_courses}: {course_name}")
                    
                    # Navigate to course page
                    try:
                        page.goto(view_url)
                        page.wait_for_load_state("networkidle")
                    except Exception as nav_error:
                        st.error(f"Error navigating to URL '{view_url}': {nav_error}")
                        continue
                    
                    # Select partner 29
                    page.locator("#partner").select_option("29")
                    # Wait for table to update
                    time.sleep(2)
                    
                    # Extract dates
                    dates = extract_course_dates(page)
                    
                    # Add to results
                    for date, location, language in dates:
                        results.append({
                            'Course Name': course_name,
                            'Date': date,
                            'Location': location,
                            'Language': language
                        })
                    
                except Exception as e:
                    st.error(f"Error processing course {course_name}: {e}")
                    continue
            
            # Final phase - 100%
            status.write("Phase 4/4: Finalizing results...")
            progress.progress(1.0)
                
        except Exception as e:
            st.error(f"Fatal error: {e}")
        finally:
            context.close()
            browser.close()
    
    return pd.DataFrame(results)

def main():
    st.title("EPIC Learning Network Course Dates Extractor")
    
    # Login form
    with st.form("login_form"):
        email = st.text_input("Email", value="")
        password = st.text_input("Password", value="", type="password")
        submit = st.form_submit_button("Start Extraction")
    
    if submit:
        # Process courses
        df = process_courses(email, password)
        
        # Show results
        if not df.empty:
            st.success("Extraction completed!")
            st.dataframe(df)
            
            # Download button
            csv = df.to_csv(index=False)
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name="course_dates.csv",
                mime="text/csv"
            )
        else:
            st.warning("No course dates were found.")

if __name__ == "__main__":
    main()