"""Explicit optional seed: python -m app.seed --email demo@example.com"""
import argparse
import getpass
from datetime import timedelta
from sqlalchemy import select
from .auth import hasher
from .database import SessionLocal
from .models import User, Interview, FollowUp, now
from .schemas import ApplicationIn
from .services import save_application


def main():
    parser = argparse.ArgumentParser(description='Create a local demo account with illustrative sample data')
    parser.add_argument('--email', default='demo@example.com')
    parser.add_argument('--name', default='Alex Morgan')
    parser.add_argument('--password', help='Local demos only; omit for a hidden password prompt')
    args = parser.parse_args()
    password = args.password or getpass.getpass('Demo password (10+ characters): ')
    if len(password) < 10:
        parser.error('Password must be at least 10 characters')
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == args.email.lower())):
            parser.error('Account already exists; no data was changed')
        user = User(name=args.name, email=args.email.lower(), password_hash=hasher.hash(password), timezone='Asia/Kolkata')
        db.add(user)
        db.flush()
        samples = [('Linear','Software Engineering Intern','Interview'),('Notion','Backend Engineering Intern','Applied'),
                   ('Figma','Product Engineering Intern','Assessment'),('Stripe','Software Engineering Intern','Applied'),
                   ('Vercel','Developer Experience Intern','Offer'),('Spotify','Backend Engineering Intern','Rejected'),
                   ('Canva','Platform Engineering Intern','Applied'),('Duolingo','Software Engineering Intern','Saved'),
                   ('Atlassian','Engineering Intern','Interview'),('Dropbox','Infrastructure Intern','Withdrawn'),
                   ('GitHub','Developer Tools Intern','Applied'),('Asana','Full Stack Intern','Saved')]
        for index, (company, role, status) in enumerate(samples):
            data = ApplicationIn(company=company, role=role, status='Saved', work_mode=['Remote','Hybrid','On-site'][index%3],
                                 location=['Remote','Bengaluru','San Francisco'][index%3],
                                 notes='Illustrative demo data — replace with your own application details.',
                                 deadline=now().date()+timedelta(days=14+index))
            item = save_application(db, user.id, data)
            if status != 'Saved':
                data = data.model_copy(update={'status':'Applied','application_date':now().date()-timedelta(days=28-index*2)})
                save_application(db, user.id, data, item)
                if status != 'Applied':
                    save_application(db, user.id, data.model_copy(update={'status':status}), item)
            if status == 'Interview':
                db.add(Interview(application_id=item.id, title='Technical conversation', type='Online', starts_at=now()+timedelta(days=1+index%3),
                                 timezone=user.timezone, venue='Meeting link pending', notes='Review your projects and prepare two questions.'))
            if status in ('Applied','Interview'):
                db.add(FollowUp(application_id=item.id, due_date=now().date()+timedelta(days=index%5-1)))
        db.commit()
    print(f'Demo account created: {args.email}. Sample companies are illustrative.')


if __name__ == '__main__':
    main()
