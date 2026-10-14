"""Sample data. Run:  python -m app.seed            (everything, idempotent)
                     python -m app.seed shows --days 7   (top up upcoming shows)

All titles, venues and organisers are fictional. No copyrighted posters are used (posters are generated gradients).
Stream content is limited to open-licensed Blender Foundation films (Creative Commons) hosted on Wikimedia Commons.
"""
import argparse
import random
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import (
    City, Coupon, Event, EventCategory, EventStaff, Faq, Genre, Initiative, Language, Movie, MovieRating, OrganizerProfile, Screen,
    Show, TicketType, User, VendorProfile, Venue, Video,
)
from app.routers.organizer import slugify
from app.services import seats as seat_svc

rng = random.Random(42)
R = 100  # rupees -> paise

LANGS = [("Hindi", "hi"), ("English", "en"), ("Telugu", "te"), ("Tamil", "ta"), ("Kannada", "kn"), ("Malayalam", "ml"),
         ("Bengali", "bn"), ("Marathi", "mr"), ("Gujarati", "gu"), ("Punjabi", "pa"), ("Odia", "or"), ("Assamese", "as"),
         ("Arabic", "ar"), ("Spanish", "es")]
GENRES = ["Drama", "Thriller", "Action", "Adventure", "Comedy", "Romance", "Fantasy", "Mystery", "Horror", "Sci-Fi", "Crime", "Family"]

# name, state, country, region, lat, lng, popular
CITIES = [
    ("Mumbai", "Maharashtra", "India", "india", 19.0760, 72.8777, True),
    ("Delhi-NCR", "Delhi", "India", "india", 28.6139, 77.2090, True),
    ("Bengaluru", "Karnataka", "India", "india", 12.9716, 77.5946, True),
    ("Hyderabad", "Telangana", "India", "india", 17.3850, 78.4867, True),
    ("Chandigarh", "Chandigarh", "India", "india", 30.7333, 76.7794, True),
    ("Ahmedabad", "Gujarat", "India", "india", 23.0225, 72.5714, True),
    ("Pune", "Maharashtra", "India", "india", 18.5204, 73.8567, True),
    ("Chennai", "Tamil Nadu", "India", "india", 13.0827, 80.2707, True),
    ("Kolkata", "West Bengal", "India", "india", 22.5726, 88.3639, True),
    ("Kochi", "Kerala", "India", "india", 9.9312, 76.2673, True),
    ("Jaipur", "Rajasthan", "India", "india", 26.9124, 75.7873, False),
    ("Lucknow", "Uttar Pradesh", "India", "india", 26.8467, 80.9462, False),
    ("Indore", "Madhya Pradesh", "India", "india", 22.7196, 75.8577, False),
    ("Bhopal", "Madhya Pradesh", "India", "india", 23.2599, 77.4126, False),
    ("Surat", "Gujarat", "India", "india", 21.1702, 72.8311, False),
    ("Nagpur", "Maharashtra", "India", "india", 21.1458, 79.0882, False),
    ("Coimbatore", "Tamil Nadu", "India", "india", 11.0168, 76.9558, False),
    ("Visakhapatnam", "Andhra Pradesh", "India", "india", 17.6868, 83.2185, False),
    ("Thiruvananthapuram", "Kerala", "India", "india", 8.5241, 76.9366, False),
    ("Goa", "Goa", "India", "india", 15.4909, 73.8278, False),
    ("Mysuru", "Karnataka", "India", "india", 12.2958, 76.6394, False),
    ("Guwahati", "Assam", "India", "india", 26.1445, 91.7362, False),
    ("Patna", "Bihar", "India", "india", 25.5941, 85.1376, False),
    ("Bhubaneswar", "Odisha", "India", "india", 20.2961, 85.8245, False),
    ("Dubai", "Dubai", "UAE", "international", 25.2048, 55.2708, False),
    ("Abu Dhabi", "Abu Dhabi", "UAE", "international", 24.4539, 54.3773, False),
    ("Singapore", "Singapore", "Singapore", "international", 1.3521, 103.8198, False),
    ("Kuala Lumpur", "KL", "Malaysia", "international", 3.1390, 101.6869, False),
    ("London", "England", "United Kingdom", "international", 51.5072, -0.1276, False),
    ("Toronto", "Ontario", "Canada", "international", 43.6532, -79.3832, False),
    ("Sydney", "NSW", "Australia", "international", -33.8688, 151.2093, False),
]
FULL_CINEMA_CITIES = {"Mumbai": 3, "Delhi-NCR": 3, "Bengaluru": 3, "Hyderabad": 3, "Chennai": 3, "Pune": 3, "Kolkata": 2,
                      "Ahmedabad": 2, "Chandigarh": 2, "Kochi": 2, "Jaipur": 2, "Lucknow": 2, "Indore": 2, "Surat": 2,
                      "Coimbatore": 2, "Visakhapatnam": 2, "Dubai": 2, "Singapore": 2, "London": 1, "Kuala Lumpur": 1}
CHAINS = {  # fictional chains; regional chains are plain config rows, admins can add more
    "default": ["Starlight Cinemas", "CineVerse", "Regal Reel"],
    "south": ["Southern Screens", "Starlight Cinemas", "Marina Multiplex"],
    "gujarat": ["Gujarat Galaxy", "CineVerse", "Starlight Cinemas"],
    "bengal": ["Bangla Bioscope", "Starlight Cinemas", "CineVerse"],
    "intl": ["Gulf Grand Cinemas", "Harbour Screens", "CineVerse"],
}
REGION_CHAIN = {"Chennai": "south", "Bengaluru": "south", "Hyderabad": "south", "Kochi": "south", "Coimbatore": "south",
                "Visakhapatnam": "south", "Ahmedabad": "gujarat", "Surat": "gujarat", "Kolkata": "bengal",
                "Dubai": "intl", "Singapore": "intl", "London": "intl", "Kuala Lumpur": "intl"}
AREAS = ["Central Plaza", "Lakeside Mall", "Riverfront", "Old Town", "Tech Park", "Airport Road", "City Centre", "Grand Bazaar"]

CATEGORIES = {
    "events": ["Music", "Workshops", "Comedy", "Kids", "Meetups", "Screenings", "Celebrity Wishes", "Talks", "Conferences", "Award Shows"],
    "plays": ["Theatre", "Street Plays", "Experimental Theatre", "Puppetry", "Mime", "Storytelling", "Improv", "Interactive Theatre", "Monologues"],
    "sports": ["Running", "Bowling", "MMA", "Basketball", "Cricket", "Horse Racing", "Sailing", "Chess", "Cycling", "Esports"],
    "activities": ["Food & Drinks", "Adventure", "Nightlife", "Quizzes", "Tourist Attractions", "Museums", "Amusement Parks", "Monuments", "Navratri Celebrations", "Tours"],
}

# title, genres, langs, minutes, cert, colors, synopsis, days_from_today_release
MOVIES = [
    ("Midnight Sonata", ["Drama", "Romance"], ["Hindi", "English"], 138, "UA", ("#1e1b4b", "#db2777"), "A retired concert pianist and a street violinist rediscover music, and each other, over one monsoon night in Mumbai.", -20),
    ("Iron Horizon", ["Action", "Sci-Fi"], ["English", "Hindi", "Telugu", "Tamil"], 152, "UA", ("#0f172a", "#f97316"), "When a rogue orbital grid threatens the planet, a disgraced pilot must fly the last prototype through the storm.", -12),
    ("The Last Monsoon", ["Drama", "Family"], ["Hindi", "Marathi"], 124, "U", ("#064e3b", "#38bdf8"), "Three generations of a Konkan farming family gather for one final harvest before the land is sold.", -30),
    ("Kaala Pahad", ["Thriller", "Crime"], ["Hindi", "Telugu"], 141, "A", ("#18181b", "#b91c1c"), "A small-town inspector chases a smuggling ring hiding inside a mining hill that has swallowed three villages.", -9),
    ("Laughing Gas", ["Comedy"], ["Hindi"], 118, "U", ("#7c2d12", "#facc15"), "A dentist, a wedding planner and a runaway goat: a wedding day goes gloriously off the rails.", -16),
    ("Neon Pharaoh", ["Adventure", "Fantasy"], ["English", "Hindi"], 129, "UA", ("#312e81", "#22d3ee"), "A neon-lit Cairo hides a doorway to a living tomb. Two archaeologists race a cult to open it first.", -6),
    ("Silent Lanterns", ["Mystery", "Horror"], ["Tamil", "Malayalam"], 112, "A", ("#111827", "#a3e635"), "Every lantern in a coastal village goes out on the same night; something is walking the shoreline.", -4),
    ("Chai & Chaos", ["Comedy", "Romance"], ["Hindi", "Gujarati"], 126, "UA", ("#78350f", "#fb7185"), "Two rival tea-stall owners in Ahmedabad are forced into a partnership by a very persuasive grandmother.", -22),
    ("Ocean of Embers", ["Adventure", "Action"], ["Telugu", "Tamil", "Kannada", "Hindi"], 163, "UA", ("#082f49", "#f59e0b"), "A salvage crew chases a legendary shipwreck across a sea that burns at dusk.", -3),
    ("Paper Kites", ["Family", "Fantasy"], ["English", "Bengali"], 98, "U", ("#1d4ed8", "#fde047"), "A girl's handmade kites carry messages to a sky city where lost wishes are kept.", -14),
    ("Dhun", ["Drama"], ["Bengali"], 135, "U", ("#365314", "#f472b6"), "A folk singer from Bolpur confronts the studio system that wants to remix her village songs.", -10),
    ("Operation Nightfall", ["Crime", "Thriller", "Action"], ["Hindi", "English"], 147, "UA", ("#020617", "#ef4444"), "Twelve hours, one tunnel, and a heist crew that has never met. The plan only works if no one trusts anyone.", -2),
    ("Starfall Protocol", ["Sci-Fi", "Thriller"], ["English"], 133, "UA", ("#0c0a09", "#8b5cf6"), "A deep-space relay receives a message from the future with one instruction: do not answer.", 14),
    ("Gully Kings", ["Comedy", "Crime"], ["Hindi"], 121, "UA", ("#422006", "#34d399"), "Four street-cricket legends become accidental con men to save their neighbourhood ground.", 21),
    ("Sapthaswaram", ["Drama", "Romance"], ["Telugu", "Kannada"], 146, "U", ("#4c1d95", "#fbbf24"), "Seven notes, seven years, and a love story that travels from Carnatic stages to Berlin jazz clubs.", 30),
    ("Whispers of the Backwaters", ["Mystery", "Drama"], ["Malayalam"], 130, "UA", ("#134e4a", "#fb923c"), "A houseboat journalist follows a trail of unsigned letters through the canals of Alappuzha.", 45),
]
YT = ["aqz-KE-bpKQ", "eRsGyueVLvQ", "R6MlUcmOul8", "TLkA0RELQ1g", "WhWc3b3KhnY", "Y-rmzh0PI3c"]  # open-licensed Blender films

W = "https://upload.wikimedia.org/wikipedia/commons/transcoded"
VIDEOS = [
    ("Big Buck Bunny", f"{W}/c/c0/Big_Buck_Bunny_4K.webm/Big_Buck_Bunny_4K.webm.480p.vp9.webm", 635, 2008, ["Comedy", "Family", "Adventure"], "English",
     "A giant rabbit takes gentle revenge on three bullying rodents.", "CC BY 3.0", "© Blender Foundation | www.bigbuckbunny.org",
     "https://commons.wikimedia.org/wiki/File:Big_Buck_Bunny_4K.webm", ("#14532d", "#fde047")),
    ("Sintel", f"{W}/f/f1/Sintel_movie_4K.webm/Sintel_movie_4K.webm.480p.vp9.webm", 888, 2010, ["Fantasy", "Adventure", "Drama"], "English",
     "A young woman searches a hostile land for the dragon she once befriended.", "CC BY 3.0", "© Blender Foundation | durian.blender.org",
     "https://commons.wikimedia.org/wiki/File:Sintel_movie_4K.webm", ("#431407", "#fb7185")),
    ("Tears of Steel", f"{W}/1/10/Tears_of_Steel_in_4k_-_Official_Blender_Foundation_release.webm/Tears_of_Steel_in_4k_-_Official_Blender_Foundation_release.webm.480p.vp9.webm", 734, 2012, ["Sci-Fi", "Action"], "English",
     "In a post-apocalyptic Amsterdam, a group of warriors and scientists try to save the world with a robot-defying experiment.", "CC BY 3.0", "(CC) Blender Foundation | mango.blender.org",
     "https://commons.wikimedia.org/wiki/File:Tears_of_Steel_in_4k_-_Official_Blender_Foundation_release.webm", ("#0c4a6e", "#f97316")),
    ("Elephants Dream", f"{W}/a/a2/Elephants_Dream_%282006%29.webm/Elephants_Dream_%282006%29.webm.480p.vp9.webm", 658, 2006, ["Sci-Fi", "Mystery"], "English",
     "Two strange characters explore a capricious and seemingly infinite machine.", "CC BY 2.5", "© 2006 Blender Foundation / Netherlands Media Art Institute | orange.blender.org",
     "https://commons.wikimedia.org/wiki/File:Elephants_Dream_(2006).webm", ("#3b0764", "#38bdf8")),
    ("Spring", f"{W}/a/a5/Spring_-_Blender_Open_Movie.webm/Spring_-_Blender_Open_Movie.webm.480p.vp9.webm", 464, 2019, ["Fantasy", "Drama"], "English",
     "The story of a shepherd girl and her dog, who face ancient spirits in order to continue the cycle of life.", "CC BY 4.0", "© Blender Foundation | cloud.blender.org/spring",
     "https://commons.wikimedia.org/wiki/File:Spring_-_Blender_Open_Movie.webm", ("#365314", "#e879f9")),
    ("Cosmos Laundromat: First Cycle", f"{W}/3/36/Cosmos_Laundromat_-_First_Cycle_-_Official_Blender_Foundation_release.webm/Cosmos_Laundromat_-_First_Cycle_-_Official_Blender_Foundation_release.webm.480p.vp9.webm", 731, 2015, ["Comedy", "Fantasy"], "English",
     "On a desolate island, a suicidal sheep named Franck meets his fate in a quirky salesman.", "CC BY-SA 3.0", "© Blender Foundation | gooseberry.blender.org",
     "https://commons.wikimedia.org/wiki/File:Cosmos_Laundromat_-_First_Cycle_-_Official_Blender_Foundation_release.webm", ("#78350f", "#2dd4bf")),
]

EVENT_TEMPLATES = [
    # section, category, title, performers, city, venue, tiers[(name, rupees, total)], days, language, flags
    ("events", "Music", "Monsoon Raga Live", ["Aarav Menon Quartet"], "Mumbai", "Riverside Arena", [("General", 799, 400), ("Gold", 1499, 150), ("VIP", 2999, 40)], 12, "Hindi", "FE"),
    ("events", "Music", "Electric Bazaar Festival", ["DJ Kaveri", "Parallel Sun", "The Bandra Collective"], "Delhi-NCR", "Open Air Grounds", [("Early Bird", 1299, 300), ("Regular", 1899, 800), ("Fan Pit", 3499, 100)], 25, "English", "FX"),
    ("events", "Music", "Carnatic Evenings", ["Lakshmi Raman"], "Chennai", "Music Academy Hall", [("Balcony", 500, 200), ("Stalls", 900, 150)], 9, "Tamil", ""),
    ("events", "Music", "Indie Sunset Sessions", ["Neel & the Nomads"], "Bengaluru", "The Loft Courtyard", [("Entry", 599, 250), ("Table of 4", 3200, 20)], 6, "English", "F"),
    ("events", "Comedy", "Stand-Up Night: Roast the Metro", ["Rohan Dutt", "Meera Iyer", "Sahil Kapoor"], "Mumbai", "Laugh Lounge", [("Standard", 499, 120), ("Premium", 899, 40)], 4, "Hindi", "F"),
    ("events", "Comedy", "Laugh Factory Hyderabad", ["Imran Qureshi"], "Hyderabad", "Cinema Hall Annex", [("Standard", 399, 150)], 8, "Telugu", ""),
    ("events", "Workshops", "Pottery for Beginners", ["Studio Mitti"], "Pune", "Mitti Studio", [("Single seat", 1200, 20)], 5, "English", ""),
    ("events", "Workshops", "Photography Walk & Workshop", ["Anjali Rao"], "Kolkata", "Victoria Memorial Lawns", [("Participant", 999, 30)], 11, "English", ""),
    ("events", "Kids", "Little Scientists Fair", ["Science Circus"], "Ahmedabad", "Science Hall", [("Child", 350, 200), ("Adult", 150, 200)], 15, "Gujarati", "F"),
    ("events", "Meetups", "Founders & Filter Coffee", ["Startup Brew"], "Bengaluru", "Cubbon Café", [("Member", 0, 80)], 3, "English", ""),
    ("events", "Screenings", "Open Movie Night: Blender Shorts", ["Community Screening"], "Kochi", "Fort Courtyard", [("Free pass", 0, 120)], 7, "English", ""),
    ("events", "Celebrity Wishes", "Birthday Shoutout by Aarav Menon", ["Aarav Menon"], "Mumbai", "Online", [("Personal video", 2499, 50)], 20, "Hindi", ""),
    ("events", "Talks", "Design Futures Talk", ["Dr. Nisha Verghese"], "Chandigarh", "Tagore Theatre", [("Standard", 300, 200)], 18, "English", ""),
    ("events", "Conferences", "DevSummit India", ["Multiple speakers"], "Bengaluru", "Convention Centre", [("Student", 999, 200), ("Professional", 4999, 600)], 40, "English", "F"),
    ("events", "Award Shows", "Regional Cinema Awards Night", ["Host: Rhea Sen"], "Hyderabad", "Grand Ballroom", [("Silver", 2500, 300), ("Platinum", 6500, 80)], 33, "Telugu", "FX"),
    ("plays", "Theatre", "Hamara Hamlet", ["Rangmanch Collective"], "Delhi-NCR", "Kamani Auditorium", [("Rear", 400, 150), ("Front", 800, 100)], 10, "Hindi", "F"),
    ("plays", "Improv", "Improv Jam: Yes, And!", ["The Spontaneous Six"], "Pune", "Black Box Theatre", [("Entry", 450, 90)], 6, "English", ""),
    ("plays", "Puppetry", "The Shadow Elephant", ["Kathputli Kala Kendra"], "Jaipur", "Jawahar Kala Kendra", [("Child", 250, 100), ("Adult", 350, 100)], 14, "Hindi", ""),
    ("plays", "Storytelling", "Tales from the Silk Route", ["Meher Contractor"], "Mumbai", "Prithvi Studio", [("Seat", 500, 70)], 9, "English", ""),
    ("plays", "Monologues", "Ek Akela: One Actor, Nine Lives", ["Vikrant Pal"], "Kolkata", "Academy of Fine Arts", [("Seat", 300, 120)], 13, "Bengali", ""),
    ("plays", "Mime", "Silence Speaks", ["Mime Troupe Mumbai"], "Mumbai", "NCPA Experimental", [("Seat", 450, 80)], 19, "English", ""),
    ("plays", "Street Plays", "Nukkad Nataks of Nagpur", ["Jagruti Manch"], "Nagpur", "Civil Lines Chowk", [("Free entry", 0, 300)], 5, "Marathi", ""),
    ("plays", "Interactive Theatre", "The Locked Room: Immersive Mystery", ["Enigma Players"], "Bengaluru", "Warehouse 9", [("Participant", 1100, 40)], 16, "English", "X"),
    ("sports", "Running", "City Half Marathon", ["Run Club India"], "Hyderabad", "Necklace Road", [("5K", 499, 1000), ("10K", 799, 800), ("21K", 1199, 500)], 28, "English", "F"),
    ("sports", "Cricket", "Corporate Cricket League Finals", ["Local teams"], "Pune", "Gahunje Ground", [("Gallery", 200, 800), ("Pavilion", 600, 200)], 17, "English", ""),
    ("sports", "Bowling", "Strike Night Tournament", ["Strike Zone"], "Delhi-NCR", "Strike Zone Arcade", [("Team of 4", 2000, 24)], 8, "English", ""),
    ("sports", "MMA", "Cage Warriors: Mumbai Fight Night", ["Fighters TBA"], "Mumbai", "Dome Arena", [("Upper", 999, 500), ("Ringside", 3999, 80)], 31, "English", "F"),
    ("sports", "Chess", "Rapid Chess Open", ["Chess Federation"], "Chennai", "Chess Hall", [("Player", 400, 128), ("Spectator", 0, 100)], 12, "English", ""),
    ("sports", "Cycling", "Sunrise Century Ride", ["Pedal Pushers"], "Bengaluru", "Nandi Hills Gate", [("Rider", 700, 300)], 21, "English", ""),
    ("sports", "Esports", "Valley Clash Esports Finals", ["Top 8 teams"], "Bengaluru", "Esports Arena", [("Day pass", 599, 400), ("Pit pass", 1499, 60)], 24, "English", "X"),
    ("sports", "Horse Racing", "Monsoon Derby Day", ["Turf Club"], "Pune", "Race Course", [("Enclosure", 500, 600), ("Club", 2500, 100)], 29, "English", ""),
    ("sports", "Sailing", "Regatta Weekend", ["Yacht Club"], "Goa", "Panaji Marina", [("Spectator", 300, 150)], 35, "English", ""),
    ("sports", "Basketball", "3x3 Street Hoops", ["Hoop Nation"], "Chandigarh", "Sector 17 Court", [("Team", 800, 32)], 10, "English", ""),
    ("activities", "Food & Drinks", "Street Food Trail", ["Guide: Chef Manpreet"], "Delhi-NCR", "Chandni Chowk Gate", [("Per person", 899, 40)], 4, "English", "F"),
    ("activities", "Adventure", "Weekend River Rafting", ["Rishikesh Rafters"], "Delhi-NCR", "Rishikesh", [("Per person", 1800, 60)], 14, "Hindi", ""),
    ("activities", "Nightlife", "Neon Rooftop Party", ["DJ Kaveri"], "Mumbai", "Sky Deck", [("Stag", 1500, 100), ("Couple", 2500, 60)], 7, "English", "X"),
    ("activities", "Quizzes", "Pub Quiz Championship", ["Quizmaster Dev"], "Pune", "The Quiz Pub", [("Team of 4", 600, 25)], 3, "English", ""),
    ("activities", "Museums", "After-Hours at the Museum", ["Curated tour"], "Kolkata", "Indian Museum", [("Adult", 250, 120), ("Student", 100, 80)], 9, "English", ""),
    ("activities", "Amusement Parks", "Aqua Kingdom Day Pass", ["Aqua Kingdom"], "Hyderabad", "Aqua Kingdom", [("Child", 600, 300), ("Adult", 900, 500)], 6, "English", ""),
    ("activities", "Monuments", "Heritage Walk: Old Delhi", ["INTACH Guide"], "Delhi-NCR", "Red Fort Gate 1", [("Per person", 400, 30)], 5, "English", ""),
    ("activities", "Navratri Celebrations", "Garba Mahotsav", ["Atul Purohit & Band"], "Ahmedabad", "GMDC Grounds", [("Single", 1200, 2000), ("Couple", 2000, 1000), ("VIP", 5000, 100)], 27, "Gujarati", "FX"),
    ("activities", "Tours", "Backwater Houseboat Day Trip", ["Kerala Tours"], "Kochi", "Alappuzha Jetty", [("Per person", 2200, 40)], 8, "Malayalam", ""),
    ("activities", "Tourist Attractions", "Sky Tower Observation Pass", ["Sky Tower"], "Dubai", "Sky Tower", [("Adult", 3500, 500)], 3, "English", ""),
]


def get_or_create(db, model, where: dict, **vals):
    obj = db.scalar(select(model).filter_by(**where))
    if not obj:
        obj = model(**where, **vals)
        db.add(obj)
        db.flush()
    return obj


def seed_reference(db):
    for n, c in LANGS:
        get_or_create(db, Language, {"code": c}, name=n)
    for g in GENRES:
        get_or_create(db, Genre, {"slug": slugify(g)}, name=g)
    for n, st, co, rg, la, ln, pop in CITIES:
        get_or_create(db, City, {"slug": slugify(n)}, name=n, state=st, country=co, region=rg, lat=la, lng=ln, is_popular=pop)
    for section, names in CATEGORIES.items():
        for n in names:
            get_or_create(db, EventCategory, {"section": section, "slug": slugify(n)}, name=n)
    db.flush()


def seed_users(db):
    admin = get_or_create(db, User, {"email": settings.admin_email}, name="Site Admin", role="admin",
                          password_hash=hash_password(settings.admin_password))
    if settings.is_prod:
        return admin, None
    org = get_or_create(db, User, {"email": "organizer@bookmyshow.example.com"}, name="Demo Organizer", role="organizer",
                        password_hash=hash_password("Organizer@12345"))
    get_or_create(db, OrganizerProfile, {"user_id": org.id}, company_name="Rangmanch Live Pvt Ltd", contact_phone="+919800000001",
                  website="https://example.com", description="Independent live-events company (sample data)", status="approved")
    get_or_create(db, User, {"email": "user@bookmyshow.example.com"}, name="Demo User", password_hash=hash_password("User@12345"))
    get_or_create(db, User, {"email": "checkin@bookmyshow.example.com"}, name="Demo Door Staff", role="checkin",
                  email_verified=True, password_hash=hash_password("Checkin@12345"))
    get_or_create(db, User, {"email": "support@bookmyshow.example.com"}, name="Demo Support Agent", role="support",
                  email_verified=True, password_hash=hash_password("Support@12345"))
    return admin, org


def seed_staff_assignments(db, organizer):
    """Demo door staff scans for all of the demo organizer's events."""
    staff = db.scalar(select(User).where(User.email == "checkin@bookmyshow.example.com"))
    if not staff or not organizer:
        return
    for eid in db.scalars(select(Event.id).where(Event.organizer_id == organizer.id)):
        get_or_create(db, EventStaff, {"event_id": eid, "user_id": staff.id}, assigned_by_id=organizer.id)


def seed_movies(db):
    langs = {l.name: l for l in db.scalars(select(Language))}
    genres = {g.name: g for g in db.scalars(select(Genre))}
    today = date.today()
    for i, (title, gs, ls, mins, cert, (a, b), syn, off) in enumerate(MOVIES):
        if db.scalar(select(Movie.id).where(Movie.slug == slugify(title))):
            continue
        m = Movie(title=title, slug=slugify(title), synopsis=syn, duration_min=mins, certificate=cert, color_a=a, color_b=b,
                  release_date=today + timedelta(days=off), trailer_youtube_id=YT[i % len(YT)],
                  cast_members=[{"name": n, "role": r} for n, r in rng.sample(
                      [("Aarav Menon", "Lead"), ("Meera Iyer", "Lead"), ("Rohan Dutt", "Supporting"), ("Nisha Verghese", "Supporting"),
                       ("Imran Qureshi", "Supporting"), ("Lakshmi Raman", "Cameo"), ("Vikrant Pal", "Villain")], 4)],
                  crew=[{"name": "Kabir Sen", "role": "Director"}, {"name": "Anika Rao", "role": "Writer"}, {"name": "Dev Malhotra", "role": "Music"}])
        m.genres = [genres[g] for g in gs]
        m.languages = [langs[l] for l in ls]
        db.add(m)
    db.flush()
    if settings.is_prod:
        return  # never fabricate ratings/users in production
    # Sample ratings from clearly-labelled demo viewers, only for released titles
    viewers = []
    for i in range(1, 9):
        viewers.append(get_or_create(db, User, {"email": f"viewer{i}@demo.example.com"}, name=f"Demo Viewer {i}"))
    for m in db.scalars(select(Movie).where(Movie.release_date <= today)):
        if db.scalar(select(func.count()).select_from(MovieRating).where(MovieRating.movie_id == m.id)):
            continue
        base = rng.uniform(5.8, 8.8)
        scores = []
        for v in rng.sample(viewers, rng.randint(4, 8)):
            s = max(1, min(10, round(rng.gauss(base, 1.1))))
            scores.append(s)
            db.add(MovieRating(user_id=v.id, movie_id=m.id, score=s))
        m.rating_avg, m.rating_count = round(sum(scores) / len(scores), 1), len(scores)


LAYOUTS = [
    {"rows": [{"label": "A", "category": "Recliner", "seats": 8, "aisles": [4]}, {"label": "B", "category": "Recliner", "seats": 8, "aisles": [4]}]
     + [{"label": c, "category": "Gold", "seats": 12, "aisles": [4, 8]} for c in "CDEF"]
     + [{"label": c, "category": "Silver", "seats": 12, "aisles": [4, 8]} for c in "GHIJ"]},
    {"rows": [{"label": c, "category": "Gold", "seats": 10, "aisles": [5]} for c in "ABCD"]
     + [{"label": c, "category": "Silver", "seats": 10, "aisles": [5]} for c in "EFGH"]},
]


def seed_cinemas(db):
    cities = {c.name: c for c in db.scalars(select(City))}
    for city_name, n in FULL_CINEMA_CITIES.items():
        city = cities[city_name]
        chains = CHAINS[REGION_CHAIN.get(city_name, "default")]
        for i in range(n):
            name = f"{chains[i % len(chains)]}: {AREAS[(i * 3 + len(city_name)) % len(AREAS)]}, {city_name}"
            v = db.scalar(select(Venue).where(Venue.name == name))
            if v:
                continue
            v = Venue(name=name, type="cinema", chain=chains[i % len(chains)], city_id=city.id,
                      address=f"{AREAS[(i * 3 + len(city_name)) % len(AREAS)]}, {city_name}",
                      lat=city.lat + rng.uniform(-0.06, 0.06), lng=city.lng + rng.uniform(-0.06, 0.06),
                      amenities=rng.sample(["Dolby Atmos", "Recliners", "Food court", "Parking", "Wheelchair access", "M-Ticket", "Cancellation"], 4))
            db.add(v)
            db.flush()
            for s in range(2):
                scr = Screen(venue_id=v.id, name=f"Screen {s + 1}", layout=LAYOUTS[s % 2])
                db.add(scr)
                db.flush()
                seat_svc.build_seats(db, scr)
    db.flush()


SLOTS = [["10:00", "13:30", "17:00", "20:30"], ["11:00", "14:30", "18:00", "21:30"]]


def schedule_shows(db, days: int = 7):
    now = datetime.now(timezone.utc)
    ist = timedelta(minutes=330)
    movies = list(db.scalars(select(Movie).where(Movie.is_active, Movie.release_date <= date.today()).order_by(Movie.id)))
    if not movies:
        return 0
    screens = list(db.execute(select(Screen, Venue, City).join(Venue, Venue.id == Screen.venue_id).join(City, City.id == Venue.city_id).order_by(Screen.id)).all())
    langs_by_name = {l.name: l for l in db.scalars(select(Language))}
    created = 0
    for si, (scr, ven, city) in enumerate(screens):
        offset = timedelta(minutes=330) if city.region == "india" else {"Dubai": timedelta(hours=4), "Abu Dhabi": timedelta(hours=4), "Singapore": timedelta(hours=8),
                                                                           "Kuala Lumpur": timedelta(hours=8), "London": timedelta(hours=0), "Toronto": timedelta(hours=-5),
                                                                           "Sydney": timedelta(hours=10)}.get(city.name, timedelta(0))
        slots = SLOTS[scr.name == "Screen 2" and 1 or 0]
        cats = seat_svc.screen_categories(db, scr.id)
        tier = 1.25 if city.name in ("Mumbai", "Delhi-NCR", "Bengaluru", "Dubai", "Singapore", "London") else 1.0
        base = {"Silver": 180, "Gold": 280, "Platinum": 400, "Recliner": 520}  # custom vendor categories fall back below
        for d in range(days):
            day = (now + ist).date() + timedelta(days=d)
            for ti, t in enumerate(slots):
                m = movies[(si * 3 + d + ti * 5) % len(movies)]
                hh, mm = map(int, t.split(":"))
                start = datetime.combine(day, time(hh, mm), tzinfo=timezone.utc) - offset
                if start <= now:
                    continue
                dur = timedelta(minutes=m.duration_min + 15)
                if db.scalar(select(Show.id).where(Show.screen_id == scr.id, Show.starts_at < start + dur, Show.ends_at > start)):
                    continue
                lang = m.languages[(si + d + ti) % len(m.languages)]
                weekend = 1.15 if day.weekday() >= 4 else 1.0
                prices = {c: int(round(base.get(c, 300) * tier * weekend / 10) * 10 * R) for c in cats}
                sh = Show(screen_id=scr.id, movie_id=m.id, language_id=lang.id, starts_at=start, ends_at=start + dur, prices=prices,
                          format=rng.choice(["2D", "2D", "3D", "IMAX 2D"]) if "Recliner" in cats else "2D")
                db.add(sh)
                db.flush()
                seat_svc.materialize_show_seats(db, sh)
                created += 1
        if si % 10 == 0:
            db.commit()
    return created


VENDOR_CHAINS = {
    "vendor@bookmyshow.example.com": ("Starlight Group Pvt Ltd", ["Starlight Cinemas", "Southern Screens", "Marina Multiplex"], "+919800000011"),
    "vendor2@bookmyshow.example.com": ("CineVerse Entertainment LLP", ["CineVerse", "Regal Reel", "Gujarat Galaxy", "Bangla Bioscope", "Gulf Grand Cinemas", "Harbour Screens"], "+919800000012"),
}


def seed_vendors(db):
    """Two approved demo vendors own the seeded cinemas; a third application and a pending theater demonstrate the approval queue."""
    if settings.is_prod:
        return
    owners = {}
    for email, (biz, chains, phone) in VENDOR_CHAINS.items():
        u = get_or_create(db, User, {"email": email}, name=biz.split(" ")[0] + " Owner", role="vendor", password_hash=hash_password("Vendor@12345"))
        vp = get_or_create(db, VendorProfile, {"user_id": u.id}, business_name=biz, contact_phone=phone, gst_number="27ABCDE1234F1Z5",
                           pan_number="ABCDE1234F", address="Head office, Mumbai (sample)", status="approved")
        for c in chains:
            owners[c] = vp
    for v in db.scalars(select(Venue).where(Venue.type == "cinema", Venue.vendor_id.is_(None))):
        if v.chain in owners:
            v.vendor_id = owners[v.chain].id
    # a vendor whose application is still pending (log in as pending-vendor@... to see the applicant view)
    pu = get_or_create(db, User, {"email": "pending-vendor@bookmyshow.example.com"}, name="Aurora Applicant", role="user", password_hash=hash_password("Vendor@12345"))
    get_or_create(db, VendorProfile, {"user_id": pu.id}, business_name="Aurora Screens LLP", contact_phone="+919800000013", status="pending",
                  description="Applying to list 3 multiplexes in Pune (sample).")
    # a theater awaiting approval from the first vendor
    first = owners["Starlight Cinemas"]
    pune = db.scalar(select(City).where(City.slug == "pune"))
    name = "Aurora Multiplex: Baner, Pune (awaiting approval)"
    if not db.scalar(select(Venue.id).where(Venue.name == name)):
        db.add(Venue(name=name, type="cinema", chain="Starlight Cinemas", city_id=pune.id, address="Baner Road, Pune", lat=18.559, lng=73.787,
                     amenities=["Dolby Atmos", "Parking"], vendor_id=first.id, approval_status="pending", submitted_at=datetime.now(timezone.utc)))
    db.flush()


def seed_events(db, organizer):
    cities = {c.name: c for c in db.scalars(select(City))}
    cats = {(c.section, c.name): c for c in db.scalars(select(EventCategory))}
    langs = {l.name: l for l in db.scalars(select(Language))}
    now = datetime.now(timezone.utc)
    palette = [("#111827", "#7c3aed"), ("#0f172a", "#f43f5e"), ("#052e16", "#facc15"), ("#1e1b4b", "#06b6d4"), ("#450a0a", "#fb923c"), ("#172554", "#34d399")]
    for sec, cat, title, performers, city, venue, tiers, days, lang, flags in EVENT_TEMPLATES:
        slug = slugify(title)
        if db.scalar(select(Event.id).where(Event.slug == slug)):
            continue
        c = cities[city]
        a, b = palette[len(title) % len(palette)]
        start = (now + timedelta(days=days)).replace(hour=rng.choice([11, 16, 18, 19, 20]), minute=0, second=0, microsecond=0)
        e = Event(organizer_id=organizer.id if organizer else None, title=title, slug=slug, section=sec,
                  category_id=cats[(sec, cat)].id, language_id=langs[lang].id, city_id=c.id, venue_name=venue,
                  address=f"{venue}, {city}", lat=c.lat + rng.uniform(-0.05, 0.05), lng=c.lng + rng.uniform(-0.05, 0.05),
                  description=f"{title}: sample listing in the {cat} category. Organised by {performers[0]}. Doors open 60 minutes before the start time. Carry a valid ID and your booking QR code.",
                  starts_at=start, ends_at=start + timedelta(hours=rng.choice([2, 3, 4])), color_a=a, color_b=b, performers=performers,
                  age_limit=rng.choice(["All ages", "5+", "16+", "18+"]), is_featured="F" in flags, is_exclusive="X" in flags, status="approved")
        for name, rupees, total in tiers:
            e.ticket_types.append(TicketType(name=name, price_paise=rupees * R, total=total, max_per_booking=10))
        db.add(e)


def seed_commerce(db):
    now = datetime.now(timezone.utc)
    coupons = [
        dict(code="WELCOME50", title="₹50 off your first booking", description="Flat ₹50 off on any booking above ₹200.", kind="general",
             discount_type="flat", value=50 * R, min_order_paise=200 * R, per_user_limit=1),
        dict(code="MOVIE20", title="20% off movie tickets", description="Up to ₹150 off on movie bookings.", kind="general",
             discount_type="percent", value=20, max_discount_paise=150 * R, applies_to="movie", per_user_limit=3),
        dict(code="LIVE15", title="15% off live events", description="Up to ₹300 off on events, plays, sports and activities.", kind="general",
             discount_type="percent", value=15, max_discount_paise=300 * R, applies_to="event", per_user_limit=3),
        dict(code="DEMOBANK10", title="10% instant discount with Demo Bank cards", description="Sample bank offer. Up to ₹100.", kind="bank",
             bank_name="Demo Bank", discount_type="percent", value=10, max_discount_paise=100 * R, per_user_limit=5),
        dict(code="CORP-ACME", title="ACME Corp employee voucher", description="Corporate voucher: ₹100 off for ACME employees.", kind="corporate",
             discount_type="flat", value=100 * R, min_order_paise=300 * R, per_user_limit=2, usage_limit=500),
        dict(code="CORP-GLOBEX", title="Globex team outing voucher", description="Corporate voucher: 25% off up to ₹500.", kind="corporate",
             discount_type="percent", value=25, max_discount_paise=500 * R, per_user_limit=2),
    ]
    for c in coupons:
        get_or_create(db, Coupon, {"code": c.pop("code")}, ends_at=now + timedelta(days=180), **c)
    for t, d, p in [("Plant a Tree", "Add ₹10 to your booking to plant a tree with our partner NGO.", "Green Earth Foundation (sample)"),
                    ("Feed a Child", "Add ₹10 to sponsor a school meal.", "Meals for All Trust (sample)")]:
        get_or_create(db, Initiative, {"title": t}, description=d, partner_name=p, amount_paise=10 * R)
    faqs = [
        ("Booking", "How do I book tickets?", "Pick a movie or event, choose your city, showtime and seats, then pay with Razorpay. Your QR ticket appears instantly under My Bookings."),
        ("Booking", "How long are my seats held?", f"Selected seats are held for {settings.seat_lock_minutes} minutes while you pay. After that they are released automatically."),
        ("Booking", "Can I cancel my booking?", f"Yes, up to {settings.cancellation_cutoff_hours} hours before the show. The ticket value is refunded; convenience fee, taxes and donations are non-refundable."),
        ("Payments", "Which payment methods are accepted?", "Cards, UPI, net banking and wallets through Razorpay. This demo runs in Razorpay test mode: no real money moves."),
        ("Payments", "My payment failed but money was debited. What now?", "Failed or late payments are refunded automatically to the original method within 5–7 working days."),
        ("Offers", "How do I use a coupon or gift card?", "Enter the code on the checkout page. Gift card balance is applied before the remaining amount is charged."),
        ("Tickets", "I didn't receive my confirmation email.", "Open My Bookings and use Resend confirmation. Your ticket is always available there with its QR code."),
        ("Organizers", "How do I list my show?", "Open ListYourShow, register your company, and once approved you can create venues, events and ticket inventory."),
        ("Account", "How do I sign in with Google?", "Use the Continue with Google button on the sign-in page. The first sign-in creates your account."),
        ("Stream", "What can I watch on Stream?", "A catalog of openly licensed films (Creative Commons). Attribution is shown on every title."),
    ]
    for i, (cat, q, a) in enumerate(faqs):
        get_or_create(db, Faq, {"question": q}, category=cat, answer=a, sort_order=i)


def seed_videos(db):
    langs = {l.name: l for l in db.scalars(select(Language))}
    genres = {g.name: g for g in db.scalars(select(Genre))}
    for i, (title, url, dur, year, gs, lang, desc, lic, attr, src, (a, b)) in enumerate(VIDEOS):
        if db.scalar(select(Video.id).where(Video.slug == slugify(title))):
            continue
        v = Video(title=title, slug=slugify(title), description=desc, video_url=url, duration_sec=dur, year=year, license=lic,
                  attribution=attr, source_url=src, language_id=langs[lang].id, color_a=a, color_b=b, is_featured=i < 3)
        v.genres = [genres[g] for g in gs]
        db.add(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", nargs="?", default="all", choices=["all", "shows"])
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args()
    with SessionLocal() as db:
        if args.what == "all":
            seed_reference(db)
            admin, org = seed_users(db)
            seed_movies(db)
            seed_cinemas(db)
            seed_vendors(db)
            seed_events(db, org or admin)
            db.flush()
            seed_staff_assignments(db, org)
            seed_commerce(db)
            seed_videos(db)
            db.commit()
        n = schedule_shows(db, args.days)
        db.commit()
        print(f"Seed complete. Shows created: {n}")


if __name__ == "__main__":
    main()
