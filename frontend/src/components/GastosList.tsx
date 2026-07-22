import { useState, useEffect } from 'react'

interface Gasto {
  id: number;
  descricao: string;
  valor: number;
  data: string;
  tipo_pagamento: string;
  parcelas: number;
  cartao_id: number;
}

interface Cartao {
  id: number;
  nome: string;
  dono: string;
}

interface GastosListProps {
  apiUrl: string;
  activeProfile: string;
}

export default function GastosList({ apiUrl, activeProfile }: GastosListProps) {
  const [gastos, setGastos] = useState<Gasto[]>([])
  const [cartoes, setCartoes] = useState<Cartao[]>([])
  const [loading, setLoading] = useState(true)
  const [mesSelecionado, setMesSelecionado] = useState(() => {
    const now = new Date()
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  })

  const formatMoney = (value: number) =>
    new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value)

  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr)
    return d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' }).replace('.', '')
  }

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      try {
        const [gastosRes, cartoesRes] = await Promise.all([
          fetch(`${apiUrl}/gastos_diarios/`),
          fetch(`${apiUrl}/cartoes/`)
        ])
        const gastosData = await gastosRes.json()
        const cartoesData = await cartoesRes.json()
        setGastos(gastosData)
        setCartoes(cartoesData)
      } catch (err) {
        console.error('Erro ao buscar gastos:', err)
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [apiUrl])

  // Filtrar cartões do perfil ativo
  const cartoesDoPerfil = cartoes.filter(c => c.dono === activeProfile)
  const cartaoIds = new Set(cartoesDoPerfil.map(c => c.id))
  const cartaoNomes = Object.fromEntries(cartoesDoPerfil.map(c => [c.id, c.nome]))

  // Filtrar gastos por perfil e mês
  const gastosFiltrados = gastos
    .filter(g => cartaoIds.has(g.cartao_id))
    .filter(g => {
      const d = new Date(g.data)
      const mesGasto = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
      return mesGasto === mesSelecionado
    })
    .sort((a, b) => new Date(b.data).getTime() - new Date(a.data).getTime())

  const totalMes = gastosFiltrados.reduce((acc, g) => acc + g.valor, 0)

  // Agrupar por dia
  const gastosPorDia: Record<string, Gasto[]> = {}
  for (const g of gastosFiltrados) {
    const dia = new Date(g.data).toLocaleDateString('pt-BR')
    if (!gastosPorDia[dia]) gastosPorDia[dia] = []
    gastosPorDia[dia].push(g)
  }

  // Gerar meses para o seletor (últimos 6 meses)
  const meses: string[] = []
  const now = new Date()
  for (let i = 0; i < 6; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
    meses.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`)
  }

  const getNomeMes = (mesStr: string) => {
    const [ano, mes] = mesStr.split('-')
    const d = new Date(Number(ano), Number(mes) - 1, 1)
    return d.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' })
  }

  const getTipoBadge = (tipo: string) => {
    switch (tipo.toLowerCase()) {
      case 'credito': return { label: 'Crédito', color: 'rgba(139, 92, 246, 0.25)', text: '#a78bfa' }
      case 'debito': return { label: 'Débito', color: 'rgba(59, 130, 246, 0.25)', text: '#93c5fd' }
      case 'pix': return { label: 'PIX', color: 'rgba(16, 185, 129, 0.25)', text: '#6ee7b7' }
      default: return { label: tipo, color: 'rgba(255,255,255,0.1)', text: '#fff' }
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('Tem certeza que deseja apagar este gasto? O valor será estornado.')) return
    try {
      await fetch(`${apiUrl}/gastos_diarios/${id}`, { method: 'DELETE' })
      setGastos(prev => prev.filter(g => g.id !== id))
    } catch (err) {
      console.error('Erro ao deletar gasto:', err)
    }
  }

  if (loading) return <p>Carregando gastos...</p>

  return (
    <div>
      {/* Seletor de Mês */}
      <div className="month-selector">
        {meses.map(mes => (
          <button
            key={mes}
            className={`month-btn ${mes === mesSelecionado ? 'active' : ''}`}
            onClick={() => setMesSelecionado(mes)}
          >
            {getNomeMes(mes)}
          </button>
        ))}
      </div>

      {/* Resumo do Mês */}
      <div className="glass-panel summary-box hover-lift transition-all" style={{ marginBottom: '1.5rem' }}>
        <span style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', textTransform: 'uppercase', letterSpacing: '1px' }}>
          Total em {getNomeMes(mesSelecionado)}
        </span>
        <span className="summary-value" style={{ color: 'var(--danger)' }}>
          {formatMoney(totalMes)}
        </span>
        <span style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
          {gastosFiltrados.length} {gastosFiltrados.length === 1 ? 'lançamento' : 'lançamentos'}
        </span>
      </div>

      {/* Lista de Gastos */}
      {gastosFiltrados.length === 0 ? (
        <div className="glass-panel" style={{ padding: '2rem', textAlign: 'center' }}>
          <p style={{ color: 'var(--text-secondary)' }}>Nenhum gasto encontrado neste mês.</p>
        </div>
      ) : (
        Object.entries(gastosPorDia).map(([dia, gastosNoDia]) => (
          <div key={dia} style={{ marginBottom: '1.5rem' }}>
            <h3 className="day-header">{dia}</h3>
            <div className="gastos-list">
              {gastosNoDia.map(gasto => {
                const badge = getTipoBadge(gasto.tipo_pagamento)
                return (
                  <div key={gasto.id} className="gasto-item glass-panel transition-all">
                    <div className="gasto-info">
                      <div className="gasto-main">
                        <span className="gasto-descricao">{gasto.descricao}</span>
                        <div className="gasto-tags">
                          <span className="gasto-badge" style={{ background: badge.color, color: badge.text }}>
                            {badge.label}
                          </span>
                          <span className="gasto-cartao">{cartaoNomes[gasto.cartao_id] || 'Cartão'}</span>
                        </div>
                      </div>
                      <div className="gasto-right">
                        <span className="gasto-valor">{formatMoney(gasto.valor)}</span>
                        <span className="gasto-data">{formatDate(gasto.data)}</span>
                        <button className="delete-btn" onClick={() => handleDelete(gasto.id)} title="Apagar gasto">
                          🗑
                        </button>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        ))
      )}
    </div>
  )
}
