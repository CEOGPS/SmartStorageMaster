import React, { useCallback, useEffect, useState } from 'react';
import SortPanel from '../components/SortPanel/SortPanel';
import RenamePanel from '../components/RenamePanel/RenamePanel';
import ChangeHistory from '../components/ChangeHistory/ChangeHistory';
import FileOrganizer from '../components/FileOrganizer/FileOrganizer';
import { listOrganizerFolders } from '../services/api';
import './Organizer.css';

/**
 * Organizer Page
 * Sort, rename, browse and move indexed files. Every change can be undone.
 */
export default function Organizer() {
  const [folders, setFolders] = useState([]);
  const [changes, setChanges] = useState(0);

  const loadFolders = useCallback(() => {
    listOrganizerFolders().then((d) => setFolders(d?.folders || [])).catch(() => setFolders([]));
  }, []);
  useEffect(() => { loadFolders(); }, [loadFolders, changes]);

  const onChanged = useCallback(() => setChanges((n) => n + 1), []);

  return (
    <div className="organizer-page">
      <div className="organizer-container">
        <h1>🗂️ Organize Files</h1>
        <p className="description">
          Sort, rename, browse and move your indexed files. Every change shows a preview first and can be undone.
        </p>
        <SortPanel folders={folders} onChanged={onChanged} />
        <RenamePanel folders={folders} onChanged={onChanged} />
        <ChangeHistory refreshKey={changes} onChanged={onChanged} />
        <FileOrganizer key={changes} />
      </div>
    </div>
  );
}
