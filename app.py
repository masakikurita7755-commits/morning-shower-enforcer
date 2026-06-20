import streamlit as st
import datetime
import time
import os
import json
import threading
from PIL import Image
from dotenv import load_dotenv

# Import our custom modules
from detector import ShowerDetector
from paypal_client import PayPalClient

# Load environment variables
load_dotenv()

# Streamlit Page Configuration
st.set_page_config(
    page_title="Morning Shower Enforcer",
    page_icon="🚿",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Custom Styling (Dark Mode / Premium Aesthetics)
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;600;700&display=swap" rel="stylesheet">
<style>
    /* Main container and font styling */
    * {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }
    .reportview-container {
        background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
    }
    
    /* Header styling */
    .title-text {
        text-align: center;
        background: linear-gradient(90deg, #60a5fa 0%, #a78bfa 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 800;
        font-size: 2.8rem;
        margin-bottom: 0.2rem;
    }
    .subtitle-text {
        text-align: center;
        color: #94a3b8;
        font-size: 1.1rem;
        margin-bottom: 2rem;
    }
    
    /* State Cards */
    .status-card {
        padding: 1.5rem;
        border-radius: 16px;
        text-align: center;
        margin-bottom: 1.5rem;
        border: 1px solid rgba(255, 255, 255, 0.1);
        box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2);
        backdrop-filter: blur(5px);
    }
    .status-pending {
        background: rgba(245, 158, 11, 0.1);
        border-color: rgba(245, 158, 11, 0.3);
        color: #fbbf24;
    }
    .status-verified {
        background: rgba(16, 185, 129, 0.1);
        border-color: rgba(16, 185, 129, 0.3);
        color: #34d399;
    }
    .status-fined {
        background: rgba(239, 68, 68, 0.1);
        border-color: rgba(239, 68, 68, 0.3);
        color: #f87171;
    }
    
    /* Box titles */
    .section-header {
        font-weight: 600;
        font-size: 1.3rem;
        color: #f1f5f9;
        margin-top: 1rem;
        margin-bottom: 0.8rem;
        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        padding-bottom: 0.4rem;
    }
</style>
""", unsafe_allow_html=True)

STATE_FILE = "app_state.json"
STATE_LOCK = threading.RLock()

# Initialize API clients
detector = ShowerDetector()
paypal = PayPalClient()

# Helper to read/write state.json atomically
def load_state():
    with STATE_LOCK:
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        
        # Default State
        default_state = {
            "status": "Pending", # Pending, Verified, Fined
            "date": str(datetime.date.today()),
            "verified_at": None,
            "fined_at": None,
            "paypal_order_id": None,
            "paypal_status": None,
            "paypal_message": None,
            "is_mock_payment": False
        }
        save_state_locked(default_state)
        return default_state

def save_state_locked(state_data):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state_data, f, indent=4)
    except Exception as e:
        print(f"Error saving state: {e}")

def update_state(updates):
    with STATE_LOCK:
        state = load_state() if os.path.exists(STATE_FILE) else {}
        state.update(updates)
        save_state_locked(state)
        return state

def reset_state():
    with STATE_LOCK:
        state = {
            "status": "Pending",
            "date": str(datetime.date.today()),
            "verified_at": None,
            "fined_at": None,
            "paypal_order_id": None,
            "paypal_status": None,
            "paypal_message": None,
            "is_mock_payment": False
        }
        save_state_locked(state)
    return state

# Check for day rollover
def check_day_rollover():
    state = load_state()
    today_str = str(datetime.date.today())
    if state.get("date") != today_str:
        # It's a new day! Reset status to Pending
        print(f"New day detected: Rollover from {state.get('date')} to {today_str}")
        new_state = {
            "status": "Pending",
            "date": today_str,
            "verified_at": None,
            "fined_at": None,
            "paypal_order_id": None,
            "paypal_status": None,
            "paypal_message": None,
            "is_mock_payment": False
        }
        update_state(new_state)

# Trigger fine routine
def trigger_fine(state):
    fine_amount = float(os.getenv("FINE_AMOUNT", "5.00"))
    fine_currency = os.getenv("FINE_CURRENCY", "USD")
    
    # Run PayPal fine execution
    result = paypal.charge_fine_sandbox(fine_amount, fine_currency)
    
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    updates = {
        "status": "Fined",
        "fined_at": timestamp,
        "paypal_order_id": result.get("order_id"),
        "paypal_status": result.get("status"),
        "paypal_message": result.get("message"),
        "is_mock_payment": result.get("is_mock", False)
    }
    
    return update_state(updates)

# Core time evaluation logic
def evaluate_deadline_check():
    check_day_rollover()
    state = load_state()
    
    # Get deadline time from env
    deadline_str = os.getenv("SHOWER_DEADLINE", "06:00")
    try:
        dh, dm = map(int, deadline_str.split(":"))
    except ValueError:
        dh, dm = 6, 0
        
    now = datetime.datetime.now()
    deadline_time = now.replace(hour=dh, minute=dm, second=0, microsecond=0)
    
    # Check if we passed 6:00 AM deadline today
    if now >= deadline_time:
        if state["status"] == "Pending":
            print(f"Deadline passed ({deadline_str}) and status is Pending. Triggering fine!")
            state = trigger_fine(state)
            
    return state, deadline_time

# Background Worker Thread (checks every 30 seconds)
class SchedulerDaemon:
    def __init__(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.running = False

    def start(self):
        if not self.running:
            self.running = True
            self.thread.start()
            print("Background Scheduler Daemon started.")

    def run(self):
        while self.running:
            try:
                evaluate_deadline_check()
            except Exception as e:
                print(f"Scheduler daemon error: {e}")
            time.sleep(30)

# Run background thread once globally via cache_resource
@st.cache_resource
def start_scheduler():
    daemon = SchedulerDaemon()
    daemon.start()
    return daemon

# Start the daemon
scheduler = start_scheduler()

# Execute initial time check on page reload
state, deadline_time = evaluate_deadline_check()

# UI Layout
st.markdown("<div class='title-text'>🚿 Shower Enforcer</div>", unsafe_allow_html=True)
st.markdown("<div class='subtitle-text'>Prove you showered by 6:00 AM, or get fined via PayPal automatically.</div>", unsafe_allow_html=True)

# ----------------- Status Section -----------------
status = state["status"]
if status == "Pending":
    st.markdown(f"""
    <div class='status-card status-pending'>
        <h2 style='margin:0; font-size:1.8rem; font-weight:700;'>⚠️ verification Pending</h2>
        <p style='margin:5px 0 0 0;'>Shower must be confirmed before {os.getenv("SHOWER_DEADLINE", "06:00")} AM</p>
    </div>
    """, unsafe_allow_html=True)
elif status == "Verified":
    st.markdown(f"""
    <div class='status-card status-verified'>
        <h2 style='margin:0; font-size:1.8rem; font-weight:700;'>✅ Shower Confirmed</h2>
        <p style='margin:5px 0 0 0;'>Verified at {state['verified_at']} today. Great job!</p>
    </div>
    """, unsafe_allow_html=True)
elif status == "Fined":
    st.markdown(f"""
    <div class='status-card status-fined'>
        <h2 style='margin:0; font-size:1.8rem; font-weight:700;'>💸 Fined Issued</h2>
        <p style='margin:5px 0 0 0;'>Deadline missed! PayPal Transaction: {state['paypal_order_id']}</p>
    </div>
    """, unsafe_allow_html=True)

# ----------------- Countdown Timer -----------------
now = datetime.datetime.now()
if status == "Pending":
    if now < deadline_time:
        time_left = deadline_time - now
        hours, remainder = divmod(time_left.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        
        st.metric(
            label="⏱️ Time remaining until deadline",
            value=time_str,
            help="Take a shower and verify before this timer hits zero!"
        )
    else:
        st.warning("Deadline has passed for today.")
else:
    st.info(f"Today's verification window is complete. Resetting at midnight ({state['date']}).")

# ----------------- Calibration Check -----------------
cal_data = detector.calibration_data
if detector.use_gemini:
    st.info("🌐 **Gemini AI Mode Active:** Multimodal analysis will be used to detect wet hair. No baseline calibration is required (though you can still save one for fallback).")
elif not cal_data:
    st.warning("⚠️ **Calibration Required:** No dry hair baseline photo found. Please calibrate first using a photo of your dry hair.")

# ----------------- Camera / Verification Section -----------------
st.markdown("<div class='section-header'>📸 Camera Verification</div>", unsafe_allow_html=True)

# Streamlit Camera Input
img_file = st.camera_input("Smile & take a photo")

if img_file:
    # Open image with PIL
    pil_img = Image.open(img_file)
    
    # Show overlay (bounding boxes)
    overlay_img = detector.get_overlay_image(pil_img)
    st.image(overlay_img, caption="Analyzed Bounding Boxes (Face in Green, Hair ROI in Blue)", use_container_width=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Calibration Button
        if st.button("💾 Save as Dry Baseline (Calibrate)", use_container_width=True):
            success, msg = detector.calibrate_baseline(pil_img)
            if success:
                st.success(msg)
                time.sleep(1.5)
                st.rerun()
            else:
                st.error(msg)
                
    with col2:
        # Verification Button
        btn_disabled = (not detector.use_gemini and not cal_data) or status != "Pending"
        btn_help = "Calibrate first!" if (not detector.use_gemini and not cal_data) else ("Shower already verified/fined today." if status != "Pending" else "Analyze hair wetness")
        
        if st.button("🚿 Verify Shower Completion", use_container_width=True, disabled=btn_disabled, help=btn_help):
            is_wet, msg, details = detector.is_wet_hair(pil_img)
            
            # Show Analysis Breakdown
            st.markdown("### Analysis Breakdown")
            
            if details.get("mode") == "gemini":
                st.info(f"**Gemini AI Analysis:** {details.get('explanation')}")
            else:
                c_bright, c_var = st.columns(2)
                # Brightness Metric
                bright_delta = f"{(details['brightness_ratio'] - 1.0)*100:.1f}%"
                c_bright.metric(
                    label="Hair Brightness", 
                    value=f"{details['current_brightness']}", 
                    delta=f"{bright_delta} vs baseline ({details['baseline_brightness']})",
                    delta_color="inverse"
                )
                # Variance Metric
                var_delta = f"{(details['variance_ratio'] - 1.0)*100:.1f}%"
                c_var.metric(
                    label="Texture Detail (Variance)", 
                    value=f"{details['current_variance']:.0f}", 
                    delta=f"{var_delta} vs baseline ({details['baseline_variance']:.0f})",
                    delta_color="inverse"
                )
            
            if is_wet:
                st.success(msg)
                # Update app state to Verified
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                update_state({
                    "status": "Verified",
                    "verified_at": timestamp
                })
                time.sleep(2)
                st.rerun()
            else:
                st.error(msg)
                if details.get("mode") != "gemini":
                    st.info("Wet hair should have darker brightness (absorbing light) and lower texture variance (clumping) compared to your dry baseline.")

# ----------------- Logs and Info Section -----------------
st.markdown("<div class='section-header'>📄 System Status & Logs</div>", unsafe_allow_html=True)
col_info1, col_info2 = st.columns(2)
with col_info1:
    st.write("**Configuration:**")
    st.write(f"- Fine Deadline: `{os.getenv('SHOWER_DEADLINE', '06:00')}` AM")
    st.write(f"- Fine Amount: `{os.getenv('FINE_AMOUNT', '5.00')} {os.getenv('FINE_CURRENCY', 'USD')}`")
    st.write(f"- Detector Mode: `{'Gemini AI (gemini-2.5-flash)' if detector.use_gemini else 'OpenCV Heuristic'}`")
    st.write(f"- PayPal Credentials Configured: `{'Yes' if paypal.is_configured() else 'No (Demo Mode Active)'}`")

with col_info2:
    st.write("**Current state details:**")
    st.write(f"- Today's Date: `{state['date']}`")
    if state['verified_at']:
        st.write(f"- Verified at: `{state['verified_at']}`")
    if state['fined_at']:
        st.write(f"- Fined at: `{state['fined_at']}`")
        st.write(f"- Order ID: `{state['paypal_order_id']}`")
        st.write(f"- PayPal Log: `{state['paypal_message']}`")

# ----------------- Sandbox Testing Panel -----------------
st.markdown("---")
with st.expander("🛠️ Testing & Debug Controls (Developer Mode)"):
    st.info("Use these controls to simulate deadline scenarios and test PayPal sandbox calls without waiting.")
    
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        if st.button("Reset Daily Status to Pending", use_container_width=True):
            reset_state()
            st.success("App state reset successfully.")
            time.sleep(1)
            st.rerun()
            
        if st.button("Force Trigger PayPal Fine immediately", use_container_width=True):
            st.write("Triggering PayPal charge call...")
            state = trigger_fine(state)
            st.success(f"Fine call completed! Check Logs below.")
            time.sleep(2.5)
            st.rerun()
            
    with col_t2:
        # Mocking time logic
        mock_deadline = st.text_input("Simulate Deadline (HH:MM)", value="06:00")
        
        # Test baseline clear
        if st.button("Delete Baseline Calibration", use_container_width=True):
            detector.clear_calibration()
            st.success("Calibration deleted.")
            time.sleep(1)
            st.rerun()
            
    # PayPal Approve Url Redirection Check
    if state.get("paypal_status") == "CREATED" and state.get("paypal_message") and "approve" in state.get("paypal_message"):
        st.warning("⚠️ **PayPal Sandbox Order Created!** Approval required.")
        approve_url = state.get("paypal_message").split("authorization at: ")[1].strip()
        st.markdown(f"[👉 Click here to login & approve the fine in Sandbox]({approve_url})")
        
        order_to_capture = state.get("paypal_order_id")
        if st.button(f"Complete Payment Capture (Order: {order_to_capture})", use_container_width=True):
            try:
                capture_res = paypal.capture_order(order_to_capture)
                update_state({
                    "paypal_status": capture_res.get("status"),
                    "paypal_message": f"Successfully Captured! Payment Status: {capture_res.get('status')}"
                })
                st.success("Payment Captured successfully!")
                time.sleep(2)
                st.rerun()
            except Exception as e:
                st.error(f"Failed to capture order: {e}")
