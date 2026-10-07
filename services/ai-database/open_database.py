#!/usr/bin/env python3
"""Open the owner's local visual database report. No server or external AI calls."""
import sys
from pathlib import Path
import uuid
import webbrowser
from ai_database import Database, default_db, read_json, report, write_new


def main():
    folder=Path(__file__).resolve().parent
    db=Database(default_db(),create=True)
    try:
        seed=folder/'starter-private.json'
        if seed.exists() and sum(db.status()['record_counts'].values())==0:
            db.bundle(read_json(seed))
        snapshot=folder/'workflow-snapshot'
        if snapshot.is_dir():
            db.import_workflow(snapshot,'Packaged GitHub workflow snapshot; see manifest.json')
            db.import_history(snapshot,'Packaged GitHub session snapshot; see manifest.json')
        output=db.path.parent/'reports'/('AI_Database_'+uuid.uuid4().hex[:12]+'.html')
        write_new(output,report(db))
        print('AI database ready. Report: '+str(output))
        webbrowser.open(output.as_uri())
        return 0
    finally:
        db.close()


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except Exception:
        print('Could not open the database. Check Python 3.10+ and the private database folder. Run the CLI status command for details.',file=sys.stderr)
        raise SystemExit(1)
