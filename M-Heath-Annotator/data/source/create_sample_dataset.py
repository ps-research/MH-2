"""
Create sample M-Help dataset for testing.
"""
import pandas as pd
from pathlib import Path


def create_sample_dataset(output_path: str = "m_help_dataset.xlsx", num_samples: int = 50):
    """
    Create sample mental health dataset.

    Args:
        output_path: Output Excel file path
        num_samples: Number of sample texts to generate
    """
    # Sample mental health texts with varying urgency levels
    sample_texts = [
        # High urgency (LEVEL_3-4)
        "I've been having thoughts about ending my life. I don't see any point in continuing.",
        "I can't stop cutting myself. It's the only way I can deal with the pain.",
        "I'm having panic attacks multiple times a day and can't leave my room.",

        # Moderate urgency (LEVEL_2-3)
        "I've been depressed for months and it's affecting my studies badly.",
        "My anxiety is so bad I can barely function anymore. I need help.",
        "I haven't slept properly in weeks and feel like I'm losing my mind.",

        # Low-moderate urgency (LEVEL_1-2)
        "I'm feeling overwhelmed with stress from exams and family pressure.",
        "I've been feeling down lately and could use someone to talk to.",
        "My relationship ended and I'm having trouble coping with it.",

        # Low urgency (LEVEL_0-1)
        "I want to learn better stress management techniques for exam season.",
        "Looking for advice on maintaining work-life balance as a student.",
        "Interested in mindfulness exercises to help with general anxiety.",

        # Therapeutic approach variations
        "I've experienced trauma in my childhood that still affects me today.",
        "I struggle with intense mood swings and difficulty managing emotions.",
        "I have trouble maintaining relationships and often feel misunderstood.",
        "I need help dealing with grief after losing a family member.",

        # Adjunct service needs
        "I think I need medication but I'm not sure where to start.",
        "My sleep problems are affecting my physical health too.",
        "I've been using alcohol to cope with my problems.",
        "I have an eating disorder and need professional help.",

        # Treatment modality variations
        "I'd prefer online therapy sessions as I have transportation issues.",
        "I think my family dynamics are contributing to my mental health issues.",
        "I'd like to join a support group for people with similar experiences.",
        "I need individual therapy but also think group sessions could help.",

        # Complex cases
        "I have ADHD and depression and they make it impossible to focus on anything.",
        "My OCD rituals are taking hours each day and I can't stop them.",
        "I experience flashbacks and nightmares from my military service.",
        "I have social anxiety so severe I can't attend classes or make friends.",

        # Crisis situations
        "I'm planning to hurt myself tonight. I can't take this anymore.",
        "I'm hearing voices telling me to harm others. I'm scared.",
        "I took some pills but I'm regretting it now. What should I do?",

        # Recovery and maintenance
        "I've been in therapy for a year and want to maintain my progress.",
        "Looking for strategies to prevent relapse of my depression.",
        "I need help transitioning from intensive therapy to regular maintenance.",

        # Specific populations
        "As an international student, I'm struggling with cultural adjustment.",
        "I'm LGBTQ+ and facing discrimination that's affecting my mental health.",
        "I'm a first-generation college student feeling imposter syndrome.",

        # Multiple comorbidities
        "I have anxiety, depression, and PTSD all at the same time.",
        "My bipolar disorder is not well controlled and affecting everything.",
        "I have both substance abuse issues and severe depression.",

        # Preventive and educational
        "I want to understand my mental health better before issues develop.",
        "Looking for psychoeducation about managing stress proactively.",
        "Interested in learning coping skills for future challenges.",

        # Relationship issues
        "My partner and I are having constant conflicts affecting my wellbeing.",
        "I'm in a toxic relationship but don't know how to leave.",
        "My family doesn't understand my mental health struggles.",

        # Academic stress
        "I'm failing all my classes due to mental health issues.",
        "The pressure to perform academically is causing severe anxiety.",
        "I need academic accommodations but don't know how to ask.",

        # Additional varied cases
        "I experience dissociation and feel disconnected from reality.",
        "My perfectionism is causing burnout and I can't stop.",
        "I have chronic pain that's worsening my depression.",
        "I'm struggling with identity issues and don't know who I am."
    ]

    # Pad to desired number with variations
    while len(sample_texts) < num_samples:
        # Add variations of existing texts
        base_text = sample_texts[len(sample_texts) % len(sample_texts)]
        sample_texts.append(base_text + " I'm not sure where to turn for help.")

    # Trim to exact number
    sample_texts = sample_texts[:num_samples]

    # Create DataFrame
    data = {
        'Sample_ID': [f'MH-{i:04d}' for i in range(num_samples)],
        'Text': sample_texts
    }

    df = pd.DataFrame(data)

    # Save to Excel
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        # Create Train, Validation, Test splits
        train_size = int(num_samples * 0.7)
        val_size = int(num_samples * 0.15)

        train_df = df.iloc[:train_size]
        val_df = df.iloc[train_size:train_size + val_size]
        test_df = df.iloc[train_size + val_size:]

        train_df.to_excel(writer, sheet_name='Train', index=False)
        val_df.to_excel(writer, sheet_name='Validation', index=False)
        test_df.to_excel(writer, sheet_name='Test', index=False)

    print(f"✅ Created sample dataset: {output_file}")
    print(f"   Train: {len(train_df)} samples")
    print(f"   Validation: {len(val_df)} samples")
    print(f"   Test: {len(test_df)} samples")
    print(f"   Total: {num_samples} samples")


if __name__ == '__main__':
    create_sample_dataset()
