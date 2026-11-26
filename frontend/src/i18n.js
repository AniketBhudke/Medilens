export const LANGS = { en: "English", hi: "हिन्दी", mr: "मराठी" };

const T = {
  en: {
    scan: "Scan", today: "Today", settings: "Settings",
    upload: "Take a photo or upload a file", uploadHint: "Prescription or blood-test report. JPG, PNG or PDF.",
    explain: "Explain in", analyze: "Read my document", reading: "Reading your document…",
    tookIt: "I took it", morning: "Morning", afternoon: "Afternoon", evening: "Evening", night: "Night",
    makeReminders: "Create reminders", noDoses: "No medicines scheduled for today.",
    saved: "Save settings", abnormal: "Outside normal range", normal: "Normal",
    verify: "Please check this with your pharmacist or doctor before taking any medicine.",
    alarmTitle: "Time for your medicine", taken: "Taken", missed: "Missed", due: "Upcoming", ringing: "Ringing",
  },
  hi: {
    scan: "स्कैन", today: "आज", settings: "सेटिंग्स",
    upload: "फोटो खींचें या फ़ाइल चुनें", uploadHint: "पर्चा या खून की जाँच की रिपोर्ट। JPG, PNG या PDF।",
    explain: "भाषा", analyze: "मेरा दस्तावेज़ पढ़ें", reading: "दस्तावेज़ पढ़ा जा रहा है…",
    tookIt: "मैंने दवा ले ली", morning: "सुबह", afternoon: "दोपहर", evening: "शाम", night: "रात",
    makeReminders: "रिमाइंडर बनाएँ", noDoses: "आज के लिए कोई दवा तय नहीं है।",
    saved: "सेटिंग्स सहेजें", abnormal: "सामान्य सीमा से बाहर", normal: "सामान्य",
    verify: "कोई भी दवा लेने से पहले कृपया अपने फार्मासिस्ट या डॉक्टर से जाँच कर लें।",
    alarmTitle: "दवा लेने का समय", taken: "ले ली", missed: "छूट गई", due: "आने वाली", ringing: "बज रहा है",
  },
  mr: {
    scan: "स्कॅन", today: "आज", settings: "सेटिंग्ज",
    upload: "फोटो काढा किंवा फाइल निवडा", uploadHint: "प्रिस्क्रिप्शन किंवा रक्त तपासणी रिपोर्ट. JPG, PNG किंवा PDF.",
    explain: "भाषा", analyze: "माझा दस्तऐवज वाचा", reading: "दस्तऐवज वाचला जात आहे…",
    tookIt: "मी औषध घेतले", morning: "सकाळ", afternoon: "दुपार", evening: "संध्याकाळ", night: "रात्र",
    makeReminders: "रिमाइंडर तयार करा", noDoses: "आजसाठी कोणतेही औषध ठरलेले नाही.",
    saved: "सेटिंग्ज जतन करा", abnormal: "सामान्य मर्यादेबाहेर", normal: "सामान्य",
    verify: "कोणतेही औषध घेण्यापूर्वी कृपया तुमच्या फार्मासिस्ट किंवा डॉक्टरांकडून तपासून घ्या.",
    alarmTitle: "औषधाची वेळ", taken: "घेतले", missed: "चुकले", due: "येणारे", ringing: "वाजत आहे",
  },
};

export const useT = (lang) => (key) => (T[lang] && T[lang][key]) || T.en[key] || key;
