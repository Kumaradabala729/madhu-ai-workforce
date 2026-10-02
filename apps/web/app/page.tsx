"use client";

import { useEffect, useState } from "react";

export default function Home() {
  const [message, setMessage] = useState("Connecting to MADHU backend...");

  useEffect(() => {
    fetch("http://127.0.0.1:8000/api/test")
      .then((response) => response.json())
      .then((data) => {
        setMessage(data.message);
      })
      .catch(() => {
        setMessage("Backend connection failed.");
      });
  }, []);

  return (
    <main className="flex min-h-screen items-center justify-center">
      <div className="text-center">
        <h1 className="text-4xl font-bold">MADHU</h1>

        <p className="mt-3 text-lg">
          AI Employees. Real Work.
        </p>

        <p className="mt-6">
          {message}
        </p>
      </div>
    </main>
  );
}