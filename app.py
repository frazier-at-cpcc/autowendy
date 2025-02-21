import streamlit as st
import pandas as pd
import re
import csv
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright, expect

async def extract_course_dates(page) -> list:
    dates = []
    try:
        # Wait for table to be visible after partner selection
        await page.wait_for_selector("table", timeout=5000)
        # Look for date elements in the table
        rows = await page.locator("table tr").all()
        for row in rows[1:]:  # Skip header row
            cells = await row.locator("td").all()
            if len(cells) >= 3:  # Ensure we have enough cells
                try:
                    date = await cells[0].inner_text()
                    location = await cells[1].inner_text()
                    language = await cells[2].inner_text()
                    if date and date.strip():  # Only add if date is not empty
                        dates.append([date.strip(), location.strip(), language.strip()])
                except Exception as e:
                    st.error(f"Error extracting row data: {e}")
                    continue
    except Exception as e:
        st.error(f"Error extracting dates: {e}")
    return dates

async def process_single_course(course_name: str, view_url: str, browser, semaphore, results):
    async with semaphore:  # Limit concurrent operations
        try:
            context = await browser.new_context()
            page = await context.new_page()
            
            # Navigate to course page
            try:
                await page.goto(view_url)
                await page.wait_for_load_state("networkidle")
            except Exception as nav_error:
                st.error(f"Error navigating to URL '{view_url}': {nav_error}")
                await context.close()
                return
            
            # Select partner 29
            await page.locator("#partner").select_option("29")
            # Wait for network to be idle after selection
            await page.wait_for_load_state("networkidle")
            
            # Extract dates
            dates = await extract_course_dates(page)
            
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
        finally:
            await context.close()

async def process_courses(email: str, password: str) -> pd.DataFrame:
    results = []
    
    # Create status containers
    status = st.empty()
    progress = st.progress(0)
    course_status = st.empty()
    
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        
        try:
            # Login phase - 10%
            status.write("Phase 1/4: Logging in...")
            progress.progress(0.05)
            
            # Create initial context for login
            context = await browser.new_context()
            page = await context.new_page()
            
            await page.goto("https://www.epiclearningnetwork.com/")
            await page.get_by_role("textbox", name="Email").fill(email)
            await page.get_by_role("textbox", name="Password").fill(password)
            await page.get_by_role("button", name="Login").click()
            progress.progress(0.1)
            
            # Navigate to courses - 20%
            status.write("Phase 2/4: Getting course list...")
            await page.get_by_role("link", name="Courses").click()
            await page.wait_for_load_state("networkidle")
            progress.progress(0.2)
            
            # Get all courses and their view links
            courses = []
            view_dates_links = await page.get_by_role("link", name=re.compile("View", re.IGNORECASE)).all()
            
            for link in view_dates_links:
                try:
                    course_row = link.locator("xpath=./..")  # Go up to the row
                    course_name = await (await course_row.locator("td").first).inner_text()
                    course_name = course_name.strip()
                    view_url = await link.get_attribute('href')
                    if view_url:
                        if not view_url.startswith('https://'):
                            view_url = f"https://www.epiclearningnetwork.com{view_url}"
                        courses.append((course_name, view_url))
                except Exception as e:
                    st.error(f"Error getting course info: {e}")
                    continue
            
            # Close initial context after getting course list
            await context.close()
            
            total_courses = len(courses)
            status.write(f"Phase 3/4: Processing {total_courses} courses...")
            
            # Create semaphore to limit concurrent operations to 3
            semaphore = asyncio.Semaphore(3)
            
            # Process courses concurrently
            tasks = []
            for course_name, view_url in courses:
                task = process_single_course(course_name, view_url, browser, semaphore, results)
                tasks.append(task)
            
            # Process in batches and update progress
            for i, task_batch in enumerate(range(0, len(tasks), 3)):
                batch = tasks[task_batch:task_batch + 3]
                await asyncio.gather(*batch)
                
                # Update progress (20% to 90% range)
                current_progress = 0.2 + (0.7 * ((i * 3 + len(batch)) / total_courses))
                progress.progress(current_progress)
                course_status.write(f"Processing courses {i * 3 + 1}-{min(i * 3 + 3, total_courses)}/{total_courses}")
            
            # Final phase - 100%
            status.write("Phase 4/4: Finalizing results...")
            progress.progress(1.0)
                
        except Exception as e:
            st.error(f"Fatal error: {e}")
        finally:
            await browser.close()
    
    return pd.DataFrame(results)

def main():
    st.title("EPIC Learning Network Course Dates Extractor")
    
    # Login form
    with st.form("login_form"):
        email = st.text_input("Email", value="")
        password = st.text_input("Password", value="", type="password")
        submit = st.form_submit_button("Start Extraction")
    
    if submit:
        # Process courses using asyncio
        df = asyncio.run(process_courses(email, password))
        
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
